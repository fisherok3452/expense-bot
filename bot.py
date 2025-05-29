import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# === Настройки ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATA_FILE = "data.json"
DAILY_LIMIT = 50
CATEGORY, AMOUNT, COMMENT = range(3)

CATEGORIES = [
    "еда", "кафе", "покупки", "алкоголь",
    "развлечения", "подарки", "здоровье", "животные", "прочее"
]

# === Загрузка/сохранение данных ===
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()

def get_today():
    return datetime.now().strftime("%Y-%m-%d")

def ensure_user_data(user_id: str):
    today = get_today()
    if user_id not in data:
        data[user_id] = {}
    if today not in data[user_id]:
        data[user_id][today] = {"balance": DAILY_LIMIT, "expenses": []}

# === Хендлеры ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Добавить трату", callback_data="add")],
        [
            InlineKeyboardButton("Баланс", callback_data="balance"),
            InlineKeyboardButton("Траты", callback_data="expenses")
        ],
        [InlineKeyboardButton("Удалить последнюю трату", callback_data="delete_last")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Добро пожаловать! Выберите действие:", reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cmd = query.data
    if cmd == "balance":
        return await balance(update, context, from_button=True)
    if cmd == "expenses":
        return await show_expenses(update, context, from_button=True)
    if cmd == "delete_last":
        return await delete_last(update, context, from_button=True)
    if cmd == "add":
        return await add_expense_start(update, context)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE, from_button=False):
    user_id = str(update.effective_user.id)
    ensure_user_data(user_id)
    today = get_today()
    bal = data[user_id][today]["balance"]
    text = f"Текущий баланс: ${bal:.2f}"
    if from_button:
        await update.callback_query.message.reply_text(text)
    else:
        await update.message.reply_text(text)

async def show_expenses(update: Update, context: ContextTypes.DEFAULT_TYPE, from_button=False):
    user_id = str(update.effective_user.id)
    ensure_user_data(user_id)
    today = get_today()
    ex = data[user_id][today]["expenses"]
    if not ex:
        text = "Сегодня ещё нет трат."
    else:
        text = "Траты за сегодня:\n" + "\n".join(
            f"- {e['category']}: ${e['amount']:.2f} — {e.get('comment','')}"
            for e in ex
        )
    if from_button:
        await update.callback_query.message.reply_text(text)
    else:
        await update.message.reply_text(text)

async def delete_last(update: Update, context: ContextTypes.DEFAULT_TYPE, from_button=False):
    user_id = str(update.effective_user.id)
    ensure_user_data(user_id)
    today = get_today()
    ex = data[user_id][today]["expenses"]
    if not ex:
        text = "Нет трат для удаления."
    else:
        last = ex.pop()
        data[user_id][today]["balance"] += last["amount"]
        save_data(data)
        text = f"Удалена последняя трата: {last['category']} на ${last['amount']:.2f}"
    if from_button:
        await update.callback_query.message.reply_text(text)
    else:
        await update.message.reply_text(text)

# --- ConversationHandler: добавление траты ---
async def add_expense_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(cat, callback_data=cat)] for cat in CATEGORIES]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("Выберите категорию:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Выберите категорию:", reply_markup=reply_markup)
    return CATEGORY

async def select_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["category"] = query.data
    await query.message.reply_text("Введите сумму:")
    return AMOUNT

async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введите корректную сумму:")
        return AMOUNT
    context.user_data["amount"] = amt
    await update.message.reply_text("Комментарий (или /skip):")
    return COMMENT

async def enter_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await save_expense(update, context, update.message.text)

async def skip_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await save_expense(update, context, "")

async def save_expense(update: Update, context: ContextTypes.DEFAULT_TYPE, comment: str):
    user_id = str(update.effective_user.id)
    ensure_user_data(user_id)
    today = get_today()
    cat = context.user_data["category"]
    amt = context.user_data["amount"]
    if amt > data[user_id][today]["balance"]:
        await update.message.reply_text("Недостаточно средств.")
    else:
        data[user_id][today]["balance"] -= amt
        data[user_id][today]["expenses"].append({
            "category": cat, "amount": amt, "comment": comment
        })
        save_data(data)
        await update.message.reply_text(f"Трата добавлена: {cat} — ${amt:.2f}")
    return ConversationHandler.END

# --- Ежедневный сброс баланса ---
def setup_daily_reset(app):
    scheduler = AsyncIOScheduler()
    def reset():
        today = get_today()
        for uid in data:
            data[uid][today] = {"balance": DAILY_LIMIT, "expenses": []}
        save_data(data)
        print(f"[RESET] Баланс сброшен: {today}")
    scheduler.add_job(reset, 'cron', hour=0, minute=0)
    scheduler.start()

async def post_init(app):
    setup_daily_reset(app)

# === Запуск ===
if __name__ == "__main__":
    app = ApplicationBuilder() \
        .token(TOKEN) \
        .post_init(post_init) \
        .build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_expense_start, pattern="^(" + "|".join(CATEGORIES) + ")$")],
        states={
            CATEGORY: [CallbackQueryHandler(select_category)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_amount)],
            COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_comment),
                CommandHandler("skip", skip_comment)
            ],
        },
        fallbacks=[CommandHandler("skip", skip_comment)],
        per_message=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(button))

    print("🚀 Бот запущен")
    app.run_polling()