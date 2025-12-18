# bot.py
# Flask app wrapped as ASGI so Railway's default uvicorn runner works.
# דרושות בתלותות: Flask, pyTelegramBotAPI, asgiref
# הוסף ל-requirements.txt: asgiref==3.8.0 uvicorn==0.22.0 (או השתמש ב-Procfile עם gunicorn)
#
# שימוש:
# - הגדר ב-Railway Secrets: TELEGRAM_BOT_TOKEN, WEBHOOK_URL (https://...),
#   WEBHOOK_SECRET (ערך ארוך ומקרי), ו-AUTO_SET_WEBHOOK=true אם רוצים שהאפליקציה תקבע את ה-webhook אוטומטית.
# - Railway מריץ את היישום עם uvicorn bot:app כברירת מחדל; לכן app הוא ASGI wrapper של Flask.

import os
import threading
import time
from flask import Flask, request, abort
import telebot

# Optional ASGI wrapper (Railway uses uvicorn by default)
try:
    from asgiref.wsgi import WsgiToAsgi
except Exception:
    WsgiToAsgi = None  # אם לא מותקן, נמשיך עם Flask WSGI (אם אתה מריץ עם gunicorn)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # למשל: https://web-production-112f6.up.railway.app
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change_this_secret")
AUTO_SET_WEBHOOK = os.getenv("AUTO_SET_WEBHOOK", "false").lower() in ("1", "true", "yes")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN must be set in environment")

if not WEBHOOK_URL:
    # לא חובה אם אתה מתכוון להגדיר את ה-webhook ידנית מחוץ לאפליקציה
    print("Warning: WEBHOOK_URL not set. You must set the webhook manually with Telegram API.")

# Flask app
flask_app = Flask(__name__)

# Telebot instance
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=True)

@bot.message_handler(func=lambda m: True)
def reply_all(message):
    try:
        if message.text:
            bot.send_message(message.chat.id, f"קיבלתי: {message.text}")
        else:
            bot.send_message(message.chat.id, "קיבלתי את ההודעה שלך — תודה!")
    except Exception as e:
        # לוג בסיסי בלבד
        print("Error sending reply:", e)

# Webhook endpoint
@flask_app.route("/webhook/<secret>", methods=["POST"])
def webhook(secret):
    if secret != WEBHOOK_SECRET:
        abort(403)
    if request.headers.get("content-type") != "application/json":
        # Telegram שולח JSON; אם זה לא JSON נדחה
        abort(403)
    update = request.get_json(force=True)
    try:
        bot.process_new_updates([telebot.types.Update.de_json(update)])
    except Exception as e:
        print("Failed to process update:", e)
    return "OK", 200

# Health endpoints (Railway בודק /health כברירת מחדל)
@flask_app.route("/healthz", methods=["GET"])
def healthz():
    return "ok", 200

@flask_app.route("/health", methods=["GET"])
def health():
    return "ok", 200

# פונקציה לקביעת ה-webhook (ניתן להריץ ידנית או לאוטומציה)
def set_webhook():
    if not WEBHOOK_URL:
        print("WEBHOOK_URL not set, skipping set_webhook()")
        return
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
    try:
        # הסר webhook קיים (במקרה) ואז קבע חדש
        bot.remove_webhook()
    except Exception as e:
        print("remove_webhook:", e)
    try:
        res = bot.set_webhook(url=webhook_url)
        print("set_webhook result:", res, "->", webhook_url)
    except Exception as e:
        print("Failed to set webhook:", e)

# אם רוצים שהאפליקציה תקבע את ה-webhook אוטומטית בזמן עלייה,
# אפשר להפעיל זאת ברקע כדי לא לחסום את השרת.
def maybe_auto_set_webhook_background():
    if AUTO_SET_WEBHOOK and WEBHOOK_URL:
        def worker():
            # המתנה קצרה כדי לאפשר לשרת לעלות במלואו
            time.sleep(1)
            try:
                set_webhook()
            except Exception as e:
                print("Auto set_webhook failed:", e)
        t = threading.Thread(target=worker, daemon=True)
        t.start()

# הפיכת Flask ל-ASGI אם asgiref זמין (כדי ש-uvicorn יוכל להריץ את היישום)
if WsgiToAsgi is not None:
    app = WsgiToAsgi(flask_app)
else:
    # אם אין asgiref, נשאיר את flask_app כ-app (לשימוש עם gunicorn)
    app = flask_app

# אם המודול מורץ כ־main (הרצה מקומית), נקבע webhook אופציונלית ונריץ Flask
if __name__ == "__main__":
    maybe_auto_set_webhook_background()
    # להרצה מקומית: python bot.py
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
else:
    # כאשר המודול מיובא על ידי uvicorn/gunicorn, ננסה להפעיל את ההגדרה האוטומטית
    # (זה מריץ רק את הפונקציה ברקע ולא חוסם את השרת)
    maybe_auto_set_webhook_background()
