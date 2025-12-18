# דרוש: pip install pyTelegramBotAPI flask
import os
from flask import Flask, request, abort
import telebot

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # הכנס כאן את הטוקן או השתמש במשתנה סביבה
WEBHOOK_URL_BASE = os.getenv("WEBHOOK_URL_BASE")  # למשל: https://yourdomain.com
WEBHOOK_URL_PATH = f"/webhook/{os.getenv('WEBHOOK_SECRET','default_secret')}"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# מטפל שמגיב לכל הודעה
@bot.message_handler(func=lambda m: True)
def reply_all(message):
    if message.text:
        bot.send_message(message.chat.id, f"קיבלתי: {message.text}")
    else:
        bot.send_message(message.chat.id, "קיבלתי את ההודעה שלך — תודה!")

# נקודת קצה ל־webhook
@app.route(WEBHOOK_URL_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') != 'application/json':
        abort(403)
    update = request.get_json(force=True)
    bot.process_new_updates([telebot.types.Update.de_json(update)])
    return "OK", 200

if __name__ == "__main__":
    # רישום ה־webhook ל־Telegram
    set_result = bot.set_webhook(url=WEBHOOK_URL_BASE + WEBHOOK_URL_PATH)
    print("set_webhook:", set_result)
    # להרצה מקומית: flask run --host=0.0.0.0 --port=8443
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8443)))
