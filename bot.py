import os
import json
import re
from datetime import datetime, timedelta
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# === Настройки ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8114366222:AAHWPOiMQIanq-DcRmNEvam5aLyxKu1AOY8")
DATA_FILE = "expenses.json"
DAILY_LIMIT = 60
CATEGORIES = [
    "Food", "Cafe", "Shopping", "Alcohol",
    "Entertainment", "Gifts", "Health", "Pets", "Other"
]

# Состояния для ConversationHandler
ADD_CATEGORY, ADD_AMOUNT, ADD_COMMENT = range(3)


# === Работа с данными ===
def load_data() -> list:
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []


def save_data(data: list):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_today_balance(data: list) -> float:
    today = datetime.now().strftime("%Y-%m-%d")
    spent = sum(e["amount"] for e in data if e["date"] == today)
    return DAILY_LIMIT - spent


# === Хендлеры ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("Add Expense")],
        [KeyboardButton("Balance"), KeyboardButton("Expenses")],
        [KeyboardButton("Stats"), KeyboardButton("Delete Last")]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Welcome! Choose an option:",
        reply_markup=markup
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    bal = get_today_balance(data)
    await update.message.reply_text(f"Today's balance: ${bal:.2f}")


async def list_expenses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    today_list = [e for e in data if e["date"] == today]
    if not today_list:
        await update.message.reply_text("No expenses today.")
        return

    msg = "Today's expenses:\n"
    for e in today_list:
        comment = f" ({e['comment']})" if e.get("comment") else ""
        msg += f"- {e['category']}: ${e['amount']:.2f}{comment} by {e['user']}\n"
    await update.message.reply_text(msg)


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    week_ago = datetime.now() - timedelta(days=7)
    weekly = [
        e for e in data
        if datetime.strptime(e["date"], "%Y-%m-%d") >= week_ago
    ]
    if not weekly:
        await update.message.reply_text("No expenses in the last 7 days.")
        return

    totals = {}
    for e in weekly:
        totals[e["category"]] = totals.get(e["category"], 0) + e["amount"]
    total = sum(totals.values())

    msg = "Stats for last 7 days:\n"
    for cat, amt in totals.items():
        percent = (amt / total) * 100
        msg += f"- {cat}: ${amt:.2f} ({percent:.1f}%)\n"
    await update.message.reply_text(msg)


async def delete_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data:
        await update.message.reply_text("No expenses to delete.")
        return
    last = data.pop()
    save_data(data)
    await update.message.reply_text(
        f"Deleted last expense: {last['category']} "
        f"${last['amount']:.2f} by {last['user']}"
    )


# --- ConversationHandler для добавления траты ---
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(cat, callback_data=cat)] for cat in CATEGORIES]
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose a category:", reply_markup=markup)
    return ADD_CATEGORY


async def add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["category"] = query.data
    await query.edit_message_text(f"Category: {query.data}\nNow enter amount in $:")
    return ADD_AMOUNT


async def add_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = float(update.message.text)
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return ADD_AMOUNT
    context.user_data["amount"] = amt
    await update.message.reply_text("Enter comment or /skip to skip:")
    return ADD_COMMENT


async def add_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["comment"] = update.message.text
    return await save_expense(update, context)


async def skip_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["comment"] = ""
    return await save_expense(update, context)


async def save_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    entry = {
        "user": update.effective_user.first_name,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "category": context.user_data["category"],
        "amount": context.user_data["amount"],
        "comment": context.user_data.get("comment", "")
    }
    data.append(entry)
    save_data(data)
    await update.message.reply_text("Expense recorded.")
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


# === Планировщик (опционально) ===
def schedule_daily_reset(app):
    scheduler = AsyncIOScheduler()
    # Пример: очищать файл каждую ночь
    # scheduler.add_job(lambda: save_data([]), 'cron', hour=0, minute=0)
    scheduler.start()


# === Запуск ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    schedule_daily_reset(app)

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_start),
            MessageHandler(filters.Regex(r"(?i)^add expense$"), add_start)
        ],
        states={
            ADD_CATEGORY: [CallbackQueryHandler(add_category)],
            ADD_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_amount)],
            ADD_COMMENT: [
                CommandHandler("skip", skip_comment),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_comment)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Регистрация хендлеров
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("expenses", list_expenses))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CommandHandler("delete", delete_last))
    app.add_handler(conv)

    # Обработка нажатий на кнопки клавиатуры
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^balance$"), balance))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^expenses$"), list_expenses))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^stats$"), show_stats))
    app.add_handler(MessageHandler(filters.Regex(r"(?i)^delete last$"), delete_last))

    print("🚀 Bot started")
    app.run_polling()