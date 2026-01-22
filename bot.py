# -*- coding: utf-8 -*-
import json
import os

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters


load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "").strip()
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()


def _format_order(data: dict) -> str:
    lines = ["📦 Позиции"]
    total = data.get("total", 0)
    for idx, item in enumerate(data.get("items", []), 1):
        title = item.get("title", "Item")
        qty = item.get("qty", 1)
        price = item.get("price", 0)
        lines.append(f"{idx}. {title} — {price} ₽ × {qty}")
    lines.append(f"\nИтого: {total} ₽")
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not WEBAPP_URL:
        await update.message.reply_text("WEBAPP_URL не задан в .env")
        return
    button = KeyboardButton(text="Открыть магазин", web_app=WebAppInfo(url=WEBAPP_URL))
    markup = ReplyKeyboardMarkup([[button]], resize_keyboard=True)
    await update.message.reply_text(
        "Открой витрину кнопкой ниже. Собери корзину и нажми «Оформить» — заказ прилетит администратору.",
        reply_markup=markup,
    )


async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not WEBAPP_URL:
        await update.message.reply_text("WEBAPP_URL не задан в .env")
        return
    button = InlineKeyboardButton(text="Открыть магазин", web_app=WebAppInfo(url=WEBAPP_URL))
    markup = InlineKeyboardMarkup([[button]])
    await update.message.reply_text("Магазин:", reply_markup=markup)


async def chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f"Ваш chat id: {update.effective_chat.id}")


async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.web_app_data:
        return
    payload = update.message.web_app_data.data
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        await update.message.reply_text("Ошибка: не удалось прочитать заказ.")
        return

    msg = _format_order(data)
    if ADMIN_CHAT_ID:
        try:
            await context.bot.send_message(chat_id=int(ADMIN_CHAT_ID), text=msg)
        except Exception:
            await update.message.reply_text("Не удалось отправить админу.")
    await update.message.reply_text("Заказ отправлен. Спасибо!")


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан. Заполни .env")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("shop", shop))
    app.add_handler(CommandHandler("id", chat_id))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))
    app.run_polling()


if __name__ == "__main__":
    main()
