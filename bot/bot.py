import os
import logging
import json
from flask import Flask, request, jsonify
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# הגדרת לוגר
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# אתחול Flask app
app = Flask(__name__)

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
application = Application.builder().token(TELECGRAM_TOKEN).build()

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

# נתיבים של Flask
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "telegram-bot",
        "webhook_set": application.bot.get_webhook_info().url == WEBHOOK_URL
    })

@app.route('/webhook', methods=['POST'])
async def webhook():
    """נקודת הכניסה ל-webhook מטלגרם"""
    if request.headers.get('X-Telegram-Bot-Api-Secret-Token') != WEBHOOK_SECRET:
        return 'Unauthorized', 403
    
    try:
        data = request.get_json()
        update = Update.de_json(data, application.bot)
        await application.initialize()
        await application.process_update(update)
        return 'OK'
    except Exception as e:
        logger.error(f"Error processing update: {e}")
        return 'Error', 500

@app.route('/set_webhook', methods=['GET', 'POST'])
def set_webhook():
    """מגדיר את ה-webhook בשרת טלגרם"""
    try:
        # הגדרת webhook
        webhook_info = application.bot.set_webhook(
            url=WEBHOOK_URL,
            secret_token=WEBHOOK_SECRET,
            max_connections=40
        )
        
        # בדיקת סטטוס
        info = application.bot.get_webhook_info()
        
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

# פונקציה לאתחול
async def initialize():
    """אתחול האפליקציה"""
    await application.initialize()
    await application.start()
    await application.updater.start_polling()  # לגיבוי, אם ה-webhook לא עובד

# הרצה
if __name__ == '__main__':
    # במצב פיתוח - הרץ עם polling
    import asyncio
    asyncio.run(initialize())
    app.run(host='0.0.0.0', port=PORT, debug=False)
else:
    # ב-production דרך gunicorn
    # מגדיר את ה-webhook בעת טעינת המודול
    import asyncio
    
    async def setup_webhook():
        try:
            await application.initialize()
            await application.bot.set_webhook(
                url=WEBHOOK_URL,
                secret_token=WEBHOOK_SECRET,
                max_connections=40
            )
            logger.info(f"Webhook set to: {WEBHOOK_URL}")
        except Exception as e:
            logger.error(f"Failed to set webhook: {e}")
    
    # הרץ את הגדרת ה-webhook
    asyncio.run(setup_webhook())
