from flask import Flask, request, abort
import os
import telebot

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://web-production-112f6.up.railway.app
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change_this_secret")

if not TOKEN or not WEBHOOK_URL:
    raise RuntimeError("Set TELEGRAM_BOT_TOKEN and WEBHOOK_URL")

bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

@bot.message_handler(func=lambda m: True)
def reply_all(message):
    if message.text:
        bot.send_message(message.chat.id, f"קיבלתי: {message.text}")
    else:
        bot.send_message(message.chat.id, "קיבלתי את ההודעה שלך — תודה!")

@app.route("/webhook/<secret>", methods=["POST"])
def webhook(secret):
    if secret != WEBHOOK_SECRET:
        abort(403)
    update = request.get_json(force=True)
    bot.process_new_updates([telebot.types.Update.de_json(update)])
    return "OK", 200

@app.route("/healthz", methods=["GET"])
def healthz():
    return "ok", 200

if __name__ == "__main__":
    # להרצה מקומית בלבד
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
