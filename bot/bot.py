import os
import logging
from flask import Flask, request, jsonify
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters

# ==================== הגדרות ====================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# משתני סביבה
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET')
PORT = int(os.environ.get('PORT', 8080))

if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN חסר!")

# יצירת בוט ודיספטשר
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, workers=0)

# ==================== פונקציות הבוט ====================
def start(update: Update, context):
    """פקודת /start"""
    update.message.reply_text(f"✅ שלום {update.effective_user.first_name}!")

def echo(update: Update, context):
    """מחזיר הודעה"""
    text = update.message.text
    update.message.reply_text(f"📝 קיבלתי: {text}")

# הוספת handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

# הגדרת webhook (אם יש URL)
if WEBHOOK_URL:
    try:
        bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET,
            max_connections=40
        )
        logger.info(f"✅ Webhook הוגדר: {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"⚠️ לא הצלחתי להגדיר webhook: {e}")

# ==================== נתיבי Flask ====================
@app.route('/')
def home():
    return jsonify({"status": "online", "bot": "running"})

@app.route('/webhook', methods=['POST'])
def webhook():
    """נקודת הכניסה מטלגרם"""
    # בדיקת סוד (אם מוגדר)
    if WEBHOOK_SECRET:
        secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
        if secret != WEBHOOK_SECRET:
            logger.warning("⚠️ בקשה עם סוד לא תקין")
            return 'Unauthorized', 403
    
    try:
        # קריאת הנתונים
        data = request.get_json()
        logger.info(f"📨 התקבלה הודעה: {data.get('message', {}).get('text', 'ללא טקסט')}")
        
        # יצירת Update וטיפול בו
        update = Update.de_json(data, bot)
        dispatcher.process_update(update)
        
        return 'OK', 200
    except Exception as e:
        logger.error(f"❌ שגיאה: {e}")
        return 'Error', 500

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/set_webhook')
def set_webhook():
    """הגדרת webhook מחדש"""
    try:
        if not WEBHOOK_URL:
            return jsonify({"error": "WEBHOOK_URL לא מוגדר"})
        
        bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET,
            max_connections=40
        )
        return jsonify({"success": True, "message": "Webhook הוגדר"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ==================== הרצה ====================
if __name__ == '__main__':
    logger.info(f"🌐 שרת Flask מתחיל על פורט {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
