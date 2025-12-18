import logging
import json
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os

# הגדרת לוגר מפורט
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # שיניתי ל-DEBUG כדי לקבל יותר פרטים
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# קבלת משתני סביבה
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET')
ADMIN_USER_ID = os.environ.get('ADMIN_USER_ID')

# בדיקת משתנים
logger.info(f"TELEGRAM_TOKEN: {'נמצא' if TELEGRAM_TOKEN else 'לא נמצא'}")
logger.info(f"WEBHOOK_URL: {WEBHOOK_URL}")
logger.info(f"WEBHOOK_SECRET: {'נמצא' if WEBHOOK_SECRET else 'לא נמצא'}")

if not TELEGRAM_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN לא הוגדר!")
    raise ValueError("TELEGRAM_BOT_TOKEN לא הוגדר")

if not WEBHOOK_URL:
    logger.error("WEBHOOK_URL לא הוגדר!")
    raise ValueError("WEBHOOK_URL לא הוגדר")

# אתחול ה-Application של טלגרם
try:
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    logger.info("יישום טלגרם אותחל בהצלחה")
except Exception as e:
    logger.error(f"שגיאה באתחול יישום טלגרם: {e}")
    raise

# הגדרת handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"פקודת /start מ-{update.effective_user.id}")
    user = update.effective_user
    await update.message.reply_text(
        f"שלום {user.first_name}!\n"
        f"ה-ID שלך הוא: {user.id}\n"
        f"הבוט פעיל ומוכן!"
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    logger.info(f"הודעה מ-{update.effective_user.id}: {text}")
    await update.message.reply_text(f"קיבלתי: {text}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"שגיאה: {context.error}", exc_info=True)

# הוספת ה-handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
application.add_error_handler(error_handler)

@app.route('/')
def home():
    return jsonify({"status": "online", "service": "telegram-bot"})

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy"})

@app.route('/webhook', methods=['POST'])
async def webhook():
    logger.info("📨 התקבלה בקשה ל-/webhook")
    logger.info(f"Headers: {dict(request.headers)}")
    
    secret_from_header = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    
    if secret_from_header != WEBHOOK_SECRET:
        logger.warning(f"סוד לא תואם! מהכותרת: {secret_from_header}, מצופה: {WEBHOOK_SECRET}")
        return 'Unauthorized', 403
    
    try:
        data = request.get_json()
        logger.info(f"נתונים שהתקבלו: {json.dumps(data)}")
        
        update = Update.de_json(data, application.bot)
        
        await application.initialize()
        await application.process_update(update)
        
        logger.info("✅ עדכון טופל בהצלחה")
        return 'OK'
    except Exception as e:
        logger.error(f"שגיאה בעיבוד עדכון: {e}", exc_info=True)
        return 'Error', 500

@app.route('/set_webhook', methods=['GET'])
def set_webhook_route():
    try:
        result = application.bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET,
            max_connections=40
        )
        
        info = application.bot.get_webhook_info()
        logger.info(f"Webhook הוגדר: {info.url}")
        
        return jsonify({
            "success": True,
            "webhook_url": info.url,
            "pending_update_count": info.pending_update_count
        })
    except Exception as e:
        logger.error(f"שגיאה בהגדרת webhook: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# אתחול webhook בעת טעינת האפליקציה
@app.before_first_request
def initialize_webhook():
    logger.info("מנסה להגדיר webhook באתחול...")
    try:
        # נסה להגדיר webhook
        application.bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET,
            max_connections=40
        )
        logger.info(f"Webhook הוגדר בהצלחה ל-{WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"לא הצלחתי להגדיר webhook באתחול: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
