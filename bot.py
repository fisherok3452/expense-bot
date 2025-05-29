import json
import logging
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackContext, ConversationHandler
)

# Настройки
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
DATA_FILE = "expenses.json"
DAILY_LIMIT = 60
CATEGORIES = ["еда", "кафе", "покупки", "алкоголь", "развлечения", "подарки", "здоровье", "животные", "прочее"]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_today_balance(data):
    today = datetime.now().strftime("%Y-%m-%d")
    total_spent = sum(e["amount"] for e in data if e["date"] == today)
    return DAILY_LIMIT - total_spent

def start(update: Update, context: CallbackContext):
    buttons = [["Добавить трату", "Баланс"], ["Траты", "Удалить последнюю трату"], ["Статистика"]]
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    update.message.reply_text("Привет! Я бот для учёта трат.", reply_markup=reply_markup)

def balance(update: Update, context: CallbackContext):
    data = load_data()
    balance = get_today_balance(data)
    update.message.reply_text(f"Текущий баланс на сегодня: ${balance:.2f}")

def list_expenses(update: Update, context: CallbackContext):
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    today_expenses = [e for e in data if e["date"] == today]
    if not today_expenses:
        update.message.reply_text("Сегодня ещё не было трат.")
        return

    msg = "Траты за сегодня:"
    
    for e in today_expenses:
        user = f'@{e["username"]}' if e["username"] else f'ID {e["user_id"]}'
        comment = f' ({e["comment"]})' if e["comment"] else ""
        msg += f'- {e["category"]}: ${e["amount"]:.2f}{comment} — {user}'
    update.message.reply_text(msg)

def delete_last_expense(update: Update, context: CallbackContext):
    data = load_data()
    if not data:
        update.message.reply_text("Список трат пуст.")
        return

    last = data.pop()
    save_data(data)
    update.message.reply_text(f"Удалена последняя трата: {last['category']} - ${last['amount']}")

def stats(update: Update, context: CallbackContext):
    data = load_data()
    week_ago = datetime.now() - timedelta(days=7)
    weekly = [e for e in data if datetime.strptime(e["date"], "%Y-%m-%d") >= week_ago]

    if not weekly:
        update.message.reply_text("За последние 7 дней трат не найдено.")
        return

    category_totals = {}
    for e in weekly:
        category_totals[e["category"]] = category_totals.get(e["category"], 0) + e["amount"]
    total = sum(category_totals.values())

    msg = "📊 Статистика за 7 дней:"
    for cat, amt in category_totals.items():
        percent = (amt / total) * 100
        msg += f"- {cat}: ${amt:.2f} ({percent:.1f}%)"

    update.message.reply_text(msg)

# --- Добавление траты ---
CHOOSING_CATEGORY, TYPING_AMOUNT, TYPING_COMMENT = range(3)

def add_expense_start(update: Update, context: CallbackContext):
    buttons = [[cat] for cat in CATEGORIES]
    reply_markup = ReplyKeyboardMarkup(buttons, one_time_keyboard=True, resize_keyboard=True)
    update.message.reply_text("Выберите категорию:", reply_markup=reply_markup)
    return CHOOSING_CATEGORY

def category_chosen(update: Update, context: CallbackContext):
    context.user_data["category"] = update.message.text
    update.message.reply_text("Введите сумму:")
    return TYPING_AMOUNT

def amount_typed(update: Update, context: CallbackContext):
    try:
        amount = float(update.message.text.replace(",", "."))
        context.user_data["amount"] = amount
    except ValueError:
        update.message.reply_text("Введите корректную сумму.")
        return TYPING_AMOUNT

    update.message.reply_text("Комментарий (опционально) или /skip:")
    return TYPING_COMMENT

def comment_typed(update: Update, context: CallbackContext):
    context.user_data["comment"] = update.message.text
    return save_expense(update, context)

def skip_comment(update: Update, context: CallbackContext):
    context.user_data["comment"] = ""
    return save_expense(update, context)

def save_expense(update: Update, context: CallbackContext):
    data = load_data()
    user = update.effective_user
    expense = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "category": context.user_data["category"],
        "amount": context.user_data["amount"],
        "comment": context.user_data.get("comment", ""),
        "user_id": user.id,
        "username": user.username or ""
    }
    data.append(expense)
    save_data(data)
    update.message.reply_text("Трата добавлена.")
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
    update.message.reply_text("Добавление отменено.")
    return ConversationHandler.END

# --- Основной запуск ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(Добавить трату)$"), add_expense_start)],
        states={
            CHOOSING_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, category_chosen)],
            TYPING_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_typed)],
            TYPING_COMMENT: [
                CommandHandler("skip", skip_comment),
                MessageHandler(filters.TEXT & ~filters.COMMAND, comment_typed)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("expenses", list_expenses))
    app.add_handler(CommandHandler("delete", delete_last_expense))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.Regex("^(Баланс)$"), balance))
    app.add_handler(MessageHandler(filters.Regex("^(Траты)$"), list_expenses))
    app.add_handler(MessageHandler(filters.Regex("^(Удалить последнюю трату)$"), delete_last_expense))
    app.add_handler(MessageHandler(filters.Regex("^(Статистика)$"), stats))
    app.add_handler(MessageHandler(filters.Regex("^(Добавить трату)$"), add_expense_start))

    print("🚀 Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
