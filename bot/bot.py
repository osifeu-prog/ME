# bot.py
# Flask WSGI app, מתאים להרצה עם gunicorn (recommended for Railway)
import os
import threading
import time
from flask import Flask, request, abort
import telebot

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # למשל: https://web-production-112f6.up.railway.app
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change_this_secret")
AUTO_SET_WEBHOOK = os.getenv("AUTO_SET_WEBHOOK", "false").lower() in ("1", "true", "yes")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN must be set in environment")

app = Flask(__name__)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=True)

# Basic handlers
@bot.message_handler(func=lambda m: True)
def reply_all(message):
    try:
        if message.text:
            bot.send_message(message.chat.id, f"קיבלתי: {message.text}")
        else:
            bot.send_message(message.chat.id, "קיבלתי את ההודעה שלך — תודה!")
    except Exception as e:
        print("Error sending reply:", e)

# Webhook endpoint
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

# Health endpoints
@app.route("/health", methods=["GET"])
def health():
    return "ok", 200

@app.route("/healthz", methods=["GET"])
def healthz():
    return "ok", 200

# set_webhook helper (safe to call once)
def set_webhook():
    if not WEBHOOK_URL:
        print("WEBHOOK_URL not set, skipping set_webhook()")
        return
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
    try:
        bot.remove_webhook()
    except Exception as e:
        print("remove_webhook:", e)
    try:
        res = bot.set_webhook(url=webhook_url)
        print("set_webhook result:", res, "->", webhook_url)
    except Exception as e:
        print("Failed to set webhook:", e)

# optional background setter (non-blocking)
def maybe_auto_set_webhook_background():
    if AUTO_SET_WEBHOOK and WEBHOOK_URL:
        def worker():
            time.sleep(1)
            try:
                set_webhook()
            except Exception as e:
                print("Auto set_webhook failed:", e)
        t = threading.Thread(target=worker, daemon=True)
        t.start()

# When run as module by gunicorn, this code will execute on import.
maybe_auto_set_webhook_background()

# If you run locally with `python bot.py`, start Flask dev server (not for prod)
if __name__ == "__main__":
    maybe_auto_set_webhook_background()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
