import os
import logging
import json
import asyncio
from threading import Thread
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==================== הגדרת לוגר ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== אתחול Flask ====================
app = Flask(__name__)

# ==================== קבלת משתני סביבה ====================
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET')
ADMIN_USER_ID = os.environ.get('ADMIN_USER_ID')
PORT = int(os.environ.get('PORT', 8080))

# ==================== אתחול אפליקציית הטלגרם ====================
# ניצור את האובייקט אבל לא נייצר לולאה כאן
application = Application.builder().token(TELEGRAM_TOKEN).build()

# ==================== הגדרת פונקציות הבוט ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"שלום {user.first_name}! 👋\n"
        f"ה-ID שלך הוא: `{user.id}`\n"
        f"הבוט פעיל ומוכן!",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📚 *פקודות זמינות:*
/start - התחל שיחה
/help - הצג הודעת עזרה זו
/id - הצג את ה-ID שלך
/admin - פקודות מנהל (למנהל בלבד)

שלח לי כל הודעה ואני אחזור עליה!
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"👤 *User ID:* `{user_id}`\n"
        f"💬 *Chat ID:* `{chat_id}`",
        parse_mode='Markdown'
    )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if ADMIN_USER_ID and user_id != ADMIN_USER_ID:
        await update.message.reply_text("⚠️ *גישה נדחית* - אתה לא מנהל!", parse_mode='Markdown')
        return
    await update.message.reply_text(
        "👑 *פקודות מנהל:*\n"
        "/stats - הצג סטטיסטיקות (בפיתוח)\n"
        "/broadcast - שליחת הודעה לכולם (בפיתוח)",
        parse_mode='Markdown'
    )

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    await update.message.reply_text(f"📝 אתה כתבת: *{user_text}*", parse_mode='Markdown')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"שגיאה בטיפול בעדכון: {context.error}", exc_info=True)
    if update and update.effective_message:
        await update.effective_message.reply_text("❌ אירעה שגיאה בעיבוד הפקודה.")

# הוספת ה-handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("id", show_id))
application.add_handler(CommandHandler("admin", admin_command))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
application.add_error_handler(error_handler)

# ==================== אתחול הבוט בלולאה נפרדת ====================
def run_bot():
    """ הרצת הבוט בלולאת אירועים נפרדת """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(application.start())
    logger.info("✅ בוט טלגרם אותחל בהצלחה")
    # הפעלת הבוט עד להפסקה
    loop.run_forever()

# התחלת אתחול הבוט ב-thread נפרד כאשר המודול נטען
# אך רק אם לא ב-test mode וכו'
if __name__ != '__main__':
    # ב-production, הפעל את הבוט ב-thread נפרד
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("Thread for bot started")

# ==================== נתיבי Flask ====================
@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "telegram-bot",
        "message": "שרת הבוט פועל",
        "webhook_url": WEBHOOK_URL
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    secret_from_header = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
    logger.info(f"📨 התקבלה בקשה ל-/webhook")

    if secret_from_header != WEBHOOK_SECRET:
        logger.warning("   ⚠️ סוד לא תואם! דוחה את הבקשה.")
        return 'Unauthorized', 403

    try:
        data = request.get_json()
        if 'message' in data:
            text = data['message'].get('text', '[ללא טקסט]')
            logger.info(f"   הודעה: '{text[:50]}...' ממשתמש {data['message']['from'].get('id')}")
        
        update = Update.de_json(data, application.bot)
        
        # שולח את העדכון לבוט לעיבוד, אבל לא מחכה לסיום (non-blocking)
        # נשתמש בלולאה הקיימת של הבוט
        future = asyncio.run_coroutine_threadsafe(application.process_update(update), application.updater._loop)
        # אפשר לחכות לתוצאה אם צריך, אבל לא חובה
        # result = future.result(timeout=10)
        
        logger.info("   ✅ עדכון נשלח לעיבוד")
        return 'OK'
    except Exception as e:
        logger.error(f"   ❌ שגיאה בעיבוד עדכון: {e}", exc_info=True)
        return 'Error', 500

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    try:
        # הגדרת ה-webhook
        # שימוש בלולאה של הבוט
        future = asyncio.run_coroutine_threadsafe(
            application.bot.set_webhook(
                url=WEBHOOK_URL,
                secret_token=WEBHOOK_SECRET,
                max_connections=40
            ), application.updater._loop
        )
        future.result(timeout=10)  # מחכים לסיום
        
        # קבלת מידע על ה-webhook
        future = asyncio.run_coroutine_threadsafe(application.bot.get_webhook_info(), application.updater._loop)
        info = future.result(timeout=10)
        
        return jsonify({
            "success": True,
            "message": "Webhook הוגדר בהצלחה",
            "details": {
                "url": info.url,
                "pending_updates": info.pending_update_count,
                "last_error": info.last_error_message,
                "ip": info.ip_address
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "service": "telegram-bot"})

# ==================== הרצה מקומית ====================
if __name__ == '__main__':
    # הרצה מקומית: מריץ את הבוט ואת Flask באותו תהליך (לא מומלץ ל-production)
    # אבל זה עבור פיתוח ובדיקה
    logger.info("🚀 מריץ את שרת Flask והבוט בפיתוח מקומי...")
    
    # הפעלת הבוט ב-thread נפרד
    bot_thread = Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # הפעלת Flask
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
