import os
import json
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from collections import defaultdict
from datetime import timedelta


# === НАСТРОЙКИ ===
TOKEN = "8114366222:AAHWPOiMQIanq-DcRmNEvam5aLyxKu1AOY8"  # экспортируй переменную TELEGRAM_BOT_TOKEN перед запуском
DATA_FILE = "data.json"
DAILY_LIMIT = 60
CATEGORY, AMOUNT, COMMENT = range(3)

CATEGORIES = [
    "еда", "кафе", "покупки", "алкоголь", "развлечения",
    "подарки", "здоровье", "животные", "прочее"
]

# === ДАННЫЕ ===
def get_today():
    return datetime.now().strftime("%Y-%m-%d")

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

data = load_data()

def ensure_user(user_id):
    today = get_today()
    if user_id not in data:
        data[user_id] = {}
    if today not in data[user_id]:
        data[user_id][today] = {
            "balance": DAILY_LIMIT,
            "expenses": []
        }

# === ОБРАБОТЧИКИ ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Добавить трату", callback_data="add")],
        [
            InlineKeyboardButton("💰 Баланс", callback_data="balance"),
            InlineKeyboardButton("📋 Траты", callback_data="expenses")
        ],
        [InlineKeyboardButton("❌ Удалить последнюю трату", callback_data="delete_last")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_choice = query.data
    user_id = str(query.from_user.id)
    ensure_user(user_id)

    if data_choice == "balance":
        bal = data[user_id][get_today()]["balance"]
        await query.message.reply_text(f"Остаток: ${bal:.2f}")
    elif data_choice == "expenses":
        expenses = data[user_id][get_today()]["expenses"]
        if not expenses:
            await query.message.reply_text("Трат пока нет.")
        else:
            msg = "\n".join([f"- {e['category']}: ${e['amount']} ({e.get('comment', '')})" for e in expenses])
            await query.message.reply_text("Сегодняшние траты:\n" + msg)
    elif data_choice == "delete_last":
        exp = data[user_id][get_today()]["expenses"]
        if exp:
            last = exp.pop()
            data[user_id][get_today()]["balance"] += last["amount"]
            save_data(data)
            await query.message.reply_text(f"Удалено: {last['category']} - ${last['amount']}")
        else:
            await query.message.reply_text("Нет трат для удаления.")
    elif data_choice == "add":
        cat_buttons = [[InlineKeyboardButton(cat, callback_data=cat)] for cat in CATEGORIES]
        markup = InlineKeyboardMarkup(cat_buttons)
        await query.message.reply_text("Выберите категорию:", reply_markup=markup)
        return CATEGORY

# === ПОШАГОВОЕ ДОБАВЛЕНИЕ ТРАТ ===
async def choose_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["category"] = query.data
    await query.message.reply_text("Введите сумму:")
    return AMOUNT

async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
        if amount <= 0:
            raise ValueError
        context.user_data["amount"] = amount
        await update.message.reply_text("Введите комментарий или /skip:")
        return COMMENT
    except:
        await update.message.reply_text("Неверная сумма. Повторите:")
        return AMOUNT

async def enter_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await finalize_expense(update, context, update.message.text)

async def skip_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await finalize_expense(update, context, "")

async def finalize_expense(update: Update, context: ContextTypes.DEFAULT_TYPE, comment):
    user_id = str(update.effective_user.id)
    ensure_user(user_id)

    today = get_today()
    amount = context.user_data["amount"]
    category = context.user_data["category"]
    balance = data[user_id][today]["balance"]

    if amount > balance:
        await update.message.reply_text("Недостаточно средств на сегодня.")
    else:
        data[user_id][today]["balance"] -= amount
        data[user_id][today]["expenses"].append({
            "amount": amount,
            "category": category,
            "comment": comment
        })
        save_data(data)

        keyboard = [
            [InlineKeyboardButton("➕ Добавить трату", callback_data="add")],
            [
                InlineKeyboardButton("💰 Баланс", callback_data="balance"),
                InlineKeyboardButton("📋 Траты", callback_data="expenses")
            ],
            [InlineKeyboardButton("❌ Удалить последнюю трату", callback_data="delete_last")]
        ]
        markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"Трата добавлена: {category} - ${amount:.2f}",
            reply_markup=markup
        )

    return ConversationHandler.END

# === СТАТИСТИКА ===
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    today = datetime.now().date()
    stats = defaultdict(float)
    total = 0.0

    for i in range(7):
        day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        day_data = data.get(user_id, {}).get(day, {}).get("expenses", [])
        for e in day_data:
            stats[e["category"]] += e["amount"]
            total += e["amount"]

    if not total:
        await update.message.reply_text("За последние 7 дней трат не найдено.")
        return

    # Формируем вывод
    lines = ["📊 Статистика за 7 дней:\n"]
    for category, amount in sorted(stats.items(), key=lambda x: -x[1]):
        percent = (amount / total) * 100
        lines.append(f"- {category.capitalize()}: ${amount:.2f} ({percent:.1f}%)")

    lines.append(f"\nИтого: ${total:.2f}")
    await update.message.reply_text("\n".join(lines))


# === АВТОСБРОС ===
def setup_daily_reset():
    scheduler = AsyncIOScheduler()

    def reset():
        today = get_today()
        for user_id in data:
            data[user_id][today] = {
                "balance": DAILY_LIMIT,
                "expenses": []
            }
        save_data(data)
        print(f"[⏰] Баланс сброшен: {today}")

    scheduler.add_job(reset, "cron", hour=0, minute=0)
    scheduler.start()

async def post_init(app):
    setup_daily_reset()

# === ЗАПУСК ===
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^add$")],
        states={
            CATEGORY: [CallbackQueryHandler(choose_category)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_amount)],
            COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_comment),
                CommandHandler("skip", skip_comment)
            ]
        },
        fallbacks=[CommandHandler("skip", skip_comment)],
        per_chat=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("stats", show_stats))

    print("🚀 Бот запущен")
    app.run_polling()
