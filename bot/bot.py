import os
import logging
from flask import Flask, request, jsonify
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters

# ==================== הגדרות ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# משתני סביבה
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET')
PORT = int(os.environ.get('PORT', 8080))

if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN חסר!")

# יצירת בוט ודיספטשר עם worker thread
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, workers=1)  # הוספת worker thread

# ==================== פונקציות הבוט ====================
def start(update: Update, context):
    """פקודת /start"""
    user = update.effective_user
    update.message.reply_text(
        f"✅ שלום {user.first_name}!\n"
        f"ה-ID שלך: {user.id}\n"
        f"הבוט פעיל ומוכן."
    )

def echo(update: Update, context):
    """מחזיר הודעה"""
    text = update.message.text
    update.message.reply_text(f"📝 אתה כתבת: {text}")

def show_id(update: Update, context):
    """מציג ID של המשתמש"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    update.message.reply_text(f"👤 User ID: {user_id}\n💬 Chat ID: {chat_id}")

# הוספת handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("id", show_id))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

# ==================== נתיבי Flask ====================
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "bot": "running",
        "webhook": WEBHOOK_URL if WEBHOOK_URL else "not_set"
    })

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
        
        # לוגים מסודרים
        if 'message' in data:
            msg = data['message']
            text = msg.get('text', '[ללא טקסט]')
            user_id = msg.get('from', {}).get('id')
            logger.info(f"📨 הודעה: '{text}' ממשתמש {user_id}")
        
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
    """הגדרת webhook מחדש - גרסה תואמת"""
    try:
        if not WEBHOOK_URL:
            return jsonify({"error": "WEBHOOK_URL לא מוגדר"})
        
        # בגרסה 13.7, set_webhook לא תומך ב-secret_token
        # אז נגדיר בלי secret_token (אבל זה בסדר כי אנחנו בודקים ב-Flask)
        result = bot.set_webhook(url=WEBHOOK_URL)
        
        return jsonify({
            "success": True,
            "message": "Webhook הוגדר (ללא secret_token)",
            "note": "הסוד נבדק ב-Flask endpoint",
            "result": str(result)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/webhook_info')
def webhook_info():
    """מציג מידע על ה-webhook הנוכחי"""
    try:
        info = bot.get_webhook_info()
        return jsonify({
            "url": info.url,
            "has_custom_certificate": info.has_custom_certificate,
            "pending_update_count": info.pending_update_count,
            "last_error_date": info.last_error_date,
            "last_error_message": info.last_error_message
        })
    except Exception as e:
        return jsonify({"error": str(e)})

# ==================== הרצה ====================
if __name__ == '__main__':
    logger.info(f"🚀 בוט טלגרם מתחיל")
    logger.info(f"🌐 שרת Flask מתחיל על פורט {PORT}")
    
    # אם יש WEBHOOK_URL, נגדיר אותו
    if WEBHOOK_URL:
        try:
            # בגרסה זו נגדיר בלי secret_token
            bot.set_webhook(url=WEBHOOK_URL)
            logger.info(f"✅ Webhook הוגדר ל: {WEBHOOK_URL}")
        except Exception as e:
            logger.warning(f"⚠️ לא הצלחתי להגדיר webhook: {e}")
    
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
