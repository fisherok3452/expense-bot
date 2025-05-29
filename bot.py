
import json
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler,
    ConversationHandler, CallbackQueryHandler, filters
)

TOKEN = "8114366222:AAHWPOiMQIanq-DcRmNEvam5aLyxKu1AOY8"

DATA_FILE = "expenses.json"
CATEGORIES = ["Food", "Cafe", "Shopping", "Alcohol", "Entertainment", "Gifts", "Health", "Pets", "Other"]
DAILY_LIMIT = 60

ADD_EXPENSE, ADD_AMOUNT, ADD_COMMENT = range(3)

def load_data():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_today_balance(data):
    today = datetime.now().strftime("%Y-%m-%d")
    total_spent = sum(e["amount"] for e in data if e["date"] == today)
    return DAILY_LIMIT - total_spent

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("➕ Add Expense")],
        [KeyboardButton("💰 Balance"), KeyboardButton("📄 Expenses")],
        [KeyboardButton("📊 Stats"), KeyboardButton("❌ Delete Last")]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Hello! I'm your expense tracking bot.", reply_markup=markup)

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    balance = get_today_balance(data)
    await update.message.reply_text(f"💰 Today's balance: ${balance:.2f}")

async def list_expenses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    today_expenses = [e for e in data if e["date"] == today]
    if not today_expenses:
        await update.message.reply_text("No expenses for today.")
        return

    msg = "📄 Today's Expenses:"
    for e in today_expenses:
        comment = f" ({e['comment']})" if e.get("comment") else ""
        msg += f"- {e['category']}: ${e['amount']:.2f}{comment} — {e['user']}"
    await update.message.reply_text(msg)

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    cutoff = datetime.now() - timedelta(days=7)
    filtered = [e for e in data if datetime.strptime(e["date"], "%Y-%m-%d") >= cutoff]

    category_totals = {}
    for e in filtered:
        category_totals[e["category"]] = category_totals.get(e["category"], 0) + e["amount"]

    total = sum(category_totals.values())
    if total == 0:
        await update.message.reply_text("No expenses in the last 7 days.")
        return

    msg = "📊 Stats for last 7 days:"
    for cat, amt in category_totals.items():
        percent = (amt / total) * 100
        msg += "- {}: ${:.2f} ({:.1f}%)\n".format(cat, amt, percent)

    await update.message.reply_text(msg)

async def delete_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data:
        await update.message.reply_text("No expenses to delete.")
        return

    last = data.pop()
    save_data(data)
    await update.message.reply_text(f"Deleted: {last['category']} ${last['amount']:.2f} by {last['user']}")

async def add_expense_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(c, callback_data=c)] for c in CATEGORIES]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose a category:", reply_markup=reply_markup)
    return ADD_EXPENSE

async def category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["category"] = query.data
    await query.edit_message_text("Category: {}
Now enter amount in $:".format(query.data))
    return ADD_AMOUNT

async def amount_typed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return ADD_AMOUNT

    context.user_data["amount"] = amount
    await update.message.reply_text("Add a comment or type /skip to skip:")
    return ADD_COMMENT

async def comment_typed(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await update.message.reply_text("Expense saved.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_expense_start),
            MessageHandler(filters.Regex("(?i)^\+? add expense"), add_expense_start)
        ],
        states={
            ADD_EXPENSE: [CallbackQueryHandler(category_chosen)],
            ADD_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount_typed)],
            ADD_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, comment_typed),
                CommandHandler("skip", skip_comment)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("expenses", list_expenses))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CommandHandler("delete", delete_last))
    app.add_handler(conv_handler)

    app.add_handler(MessageHandler(filters.Regex("(?i)^balance"), balance))
    app.add_handler(MessageHandler(filters.Regex("(?i)^expenses"), list_expenses))
    app.add_handler(MessageHandler(filters.Regex("(?i)^stats"), show_stats))
    app.add_handler(MessageHandler(filters.Regex("(?i)^delete"), delete_last))

    app.run_polling()

if __name__ == "__main__":
    main()
