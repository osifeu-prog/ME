import os
import logging
from threading import Thread
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== הגדרות בסיסיות ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# אפליקציית Flask
app = Flask(__name__)

# קבלת משתנים
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET')
PORT = int(os.environ.get('PORT', 8080))

# בדיקות בסיסיות
if not TELEGRAM_TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN חסר!")
if not WEBHOOK_URL:
    raise ValueError("❌ WEBHOOK_URL חסר!")

# ==================== פונקציות הבוט ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודת /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"✅ שלום {user.first_name}!\n"
        f"הבוט שלך פועל בהצלחה!"
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מחזיר הודעה"""
    text = update.message.text
    await update.message.reply_text(f"📝 קיבלתי: {text}")

# ==================== אתחול והרצת הבוט ====================
def run_bot():
    """מפעיל את הבוט ב-thread נפרד"""
    try:
        # יצירת האפליקציה
        bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
        
        # הוספת handlers
        bot_app.add_handler(CommandHandler("start", start))
        bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
        
        # הגדרת webhook
        bot_app.bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET,
            max_connections=40
        )
        
        logger.info(f"✅ בוט הוגדר עם webhook: {WEBHOOK_URL}")
        
        # הרצת הבוט
        bot_app.run_polling()
        
    except Exception as e:
        logger.error(f"❌ שגיאה בבוט: {e}")

# הפעלת הבוט ב-thread נפרד
bot_thread = Thread(target=run_bot, daemon=True)
bot_thread.start()
logger.info("🚀 בוט התחיל לרוץ ב-background")

# ==================== נתיבי Flask ====================
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "bot": "running",
        "webhook": WEBHOOK_URL
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """נקודת הכניסה היחידה מטלגרם"""
    # בדיקת סוד
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != WEBHOOK_SECRET:
        logger.warning("⚠️ בקשה עם סוד לא תקין")
        return 'Unauthorized', 403
    
    try:
        # העברת הבקשה ישירות לבוט
        # הבוט כבר מטפל בה דרך webhook
        return 'OK'
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
        from telegram import Bot
        bot = Bot(token=TELEGRAM_TOKEN)
        result = bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET
        )
        return jsonify({"success": True, "result": str(result)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ==================== הרצה ====================
if __name__ == '__main__':
    logger.info(f"🌐 שרת Flask מתחיל על פורט {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
