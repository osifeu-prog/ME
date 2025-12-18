# bot.py
# Flask app שמקבל webhook מ‑Telegram ומגיב לכל הודעה
import os
from flask import Flask, request, abort
import telebot

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_BASE = os.getenv("WEBHOOK_URL")  # למשל: https://web-production-112f6.up.railway.app
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "default_secret")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
if not WEBHOOK_BASE:
    raise RuntimeError("WEBHOOK_URL is not set")

bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

@bot.message_handler(func=lambda m: True)
def reply_all(message):
    try:
        if message.text:
            bot.send_message(message.chat.id, f"קיבלתי: {message.text}")
        else:
            bot.send_message(message.chat.id, "קיבלתי את ההודעה שלך — תודה!")
    except Exception as e:
        # אל תשלח שגיאות למשתמש; רק לוג
        print("Error replying:", e)

@app.route("/webhook/<secret>", methods=["POST"])
def webhook(secret):
    if secret != WEBHOOK_SECRET:
        abort(403)
    if request.headers.get("content-type") != "application/json":
        abort(403)
    update = request.get_json(force=True)
    try:
        bot.process_new_updates([telebot.types.Update.de_json(update)])
    except Exception as e:
        print("Failed to process update:", e)
    return "OK", 200

@app.route("/healthz", methods=["GET"])
def healthz():
    return "ok", 200

def set_webhook():
    webhook_url = f"{WEBHOOK_BASE.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
    # הסר webhook קיים ואז קבע חדש
    try:
        bot.remove_webhook()
    except Exception as e:
        print("remove_webhook:", e)
    try:
        res = bot.set_webhook(url=webhook_url)
        print("set_webhook result:", res, "->", webhook_url)
    except Exception as e:
        print("Failed to set webhook:", e)

if __name__ == "__main__":
    # להרצה מקומית בלבד
    set_webhook()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
