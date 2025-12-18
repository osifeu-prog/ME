import os
import logging
import json
import asyncio
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# הגדרת לוגר
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# אתחול Flask app
app = Flask(__name__)
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

# קבלת משתני סביבה
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET')
ADMIN_USER_ID = os.environ.get('ADMIN_USER_ID')
PORT = int(os.environ.get('PORT', 8080))

# בדיקה שהמשתנים הנדרשים קיימים
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN לא הוגדר")
if not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL לא הוגדר")

# אתחול ה-Application של טלגרם
application = Application.builder().token(TELEGRAM_TOKEN).build()

# הגדרת handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """שולח הודעה כשהמשתמש מפעיל /start"""
    user = update.effective_user
    await update.message.reply_text(
        f"שלום {user.first_name}!\n"
        f"ה-ID שלך הוא: {user.id}\n"
        f"הבוט פעיל ומוכן!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """שולח הודעת עזרה"""
    help_text = """
    פקודות זמינות:
    /start - התחל שיחה
    /help - הצג הודעת עזרה
    /id - הצג את ה-ID שלך
    /admin - פקודות מנהל (למנהל בלבד)
    """
    await update.message.reply_text(help_text)

async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מציג את ה-ID של המשתמש"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"👤 User ID: {user_id}\n"
        f"💬 Chat ID: {chat_id}"
    )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """פקודות מנהל"""
    user_id = update.effective_user.id
    
    if str(user_id) != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ גישה נדחית - אתה לא מנהל!")
        return
    
    await update.message.reply_text(
        "👑 פקודות מנהל:\n"
        "/stats - סטטיסטיקות\n"
        "/broadcast - שליחת הודעה לכולם"
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """מחזיר את ההודעה שהמשתמש שלח"""
    text = update.message.text
    await update.message.reply_text(f"קיבלתי: {text}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """טיפול בשגיאות"""
    logger.error(f"שגיאה: {context.error}")

# הוספת ה-handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("id", show_id))
application.add_handler(CommandHandler("admin", admin_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
application.add_error_handler(error_handler)

# אתחול האפליקציה של טלגרם
async def initialize_bot():
    """אתחול האפליקציה של הטלגרם בוט"""
    await application.initialize()
    await application.start()
    logger.info("בוט טלגרם אותחל בהצלחה")

# הרץ את אתחול הבוט
try:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(initialize_bot())
    logger.info("בוט טלגרם מוכן לקבל עדכונים")
except Exception as e:
    logger.error(f"שגיאה באתחול הבוט: {e}")

# נתיבים של Flask
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "telegram-bot",
        "webhook_url": WEBHOOK_URL
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """נקודת הכניסה ל-webhook מטלגרם"""
    secret_from_header = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    logger.info(f"📨 התקבלה בקשה ל-/webhook")
    
    if secret_from_header != WEBHOOK_SECRET:
        logger.warning("⚠️ סוד לא תואם! דוחה את הבקשה.")
        return 'Unauthorized', 403
    
    try:
        # המרת הנתונים לעדכון של טלגרם
        update_data = request.get_json()
        update = Update.de_json(update_data, application.bot)
        
        # הוסף את העדכון לתור העיבוד של האפליקציה
        # שימוש ב-run_until_complete מכיוון שאנחנו בתוך פונקציה סינכרונית
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.process_update(update))
        
        logger.info("✅ עדכון טופל בהצלחה")
        return 'OK'
    except Exception as e:
        logger.error(f"❌ שגיאה בעיבוד עדכון: {e}", exc_info=True)
        return 'Error', 500

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    """מגדיר את ה-webhook בשרת טלגרם"""
    try:
        # הגדרת webhook
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            application.bot.set_webhook(
                url=WEBHOOK_URL,
                secret_token=WEBHOOK_SECRET,
                max_connections=40
            )
        )
        
        # בדיקת סטטוס
        info = loop.run_until_complete(application.bot.get_webhook_info())
        
        return jsonify({
            "success": True,
            "webhook_url": info.url,
            "has_custom_certificate": info.has_custom_certificate,
            "pending_update_count": info.pending_update_count,
            "max_connections": info.max_connections,
            "ip_address": info.ip_address
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/health')
def health_check():
    """בדיקת בריאות"""
    return jsonify({"status": "healthy", "service": "telegram-bot"})

@app.route('/test', methods=['POST', 'GET'])
def test_webhook():
    """נתיב לבדיקת webhook"""
    if request.method == 'GET':
        return jsonify({"message": "Use POST to test webhook"})
    
    # מדמה בקשה מטלגרם
    test_data = {
        "update_id": 10000,
        "message": {
            "message_id": 1,
            "from": {
                "id": 123456789,
                "first_name": "Test",
                "is_bot": False
            },
            "chat": {
                "id": 123456789,
                "first_name": "Test",
                "type": "private"
            },
            "date": 1600000000,
            "text": "/start"
        }
    }
    
    # שולח את הנתונים לעצמו
    response = app.test_client().post(
        '/webhook',
        json=test_data,
        headers={'X-Telegram-Bot-Api-Secret-Token': WEBHOOK_SECRET}
    )
    
    return jsonify({
        "status": response.status_code,
        "data": response.get_json() if response.is_json else response.data.decode()
    })

# הרצה ישירה לצורך פיתוח
if __name__ == '__main__':
    # במצב פיתוח - הגדר webhook
    async def dev_setup():
        await application.initialize()
        await application.start()
        # הגדר webhook ל-localhost לצורך בדיקה
        await application.bot.set_webhook(
            url="https://me-production-8bf5.up.railway.app/webhook",
            secret_token=WEBHOOK_SECRET,
            max_connections=40
        )
        logger.info("Webhook הוגדר בהצלחה לפתחון")
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(dev_setup())
    except Exception as e:
        logger.error(f"שגיאה בהגדרת webhook לפתחון: {e}")
    
    app.run(host='0.0.0.0', port=PORT, debug=False)
