from flask import Flask, request, abort
import os
import telebot

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@bot.message_handler(func=lambda m: True)
def reply_all(message):
    if message.text:
        bot.send_message(message.chat.id, f"קיבלתי: {message.text}")
    else:
        bot.send_message(message.chat.id, "קיבלתי את ההודעה שלך — תודה!")

@app.route("/webhook/<secret>", methods=["POST"])
def webhook(secret):
    expected = os.getenv("WEBHOOK_SECRET", "default_secret")
    if secret != expected:
        abort(403)
    if request.headers.get("content-type") != "application/json":
        abort(403)
    update = request.get_json(force=True)
    bot.process_new_updates([telebot.types.Update.de_json(update)])
    return "OK", 200

if __name__ == "__main__":
    # רק להרצה מקומית (לא בשימוש ב‑gunicorn)
    app.run(host="0.0.0.0", port=8000)
