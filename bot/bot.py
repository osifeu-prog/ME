import os
import logging
import json
from datetime import datetime
from flask import Flask, request, jsonify
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters

# ==================== CONFIGURATION ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Environment variables
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET')
ADMIN_USER_ID = os.environ.get('ADMIN_USER_ID', '').strip()
PORT = int(os.environ.get('PORT', 8080))

# Validation
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN is required!")

# Bot initialization
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, workers=2)

# Simple stats tracking
bot_stats = {
    'start_count': 0,
    'message_count': 0,
    'users': set(),
    'start_time': datetime.now().isoformat()
}

# ==================== HELPER FUNCTIONS ====================
def is_admin(user_id):
    """Check if user is admin"""
    return ADMIN_USER_ID and str(user_id) == ADMIN_USER_ID

def log_message(update, command=None):
    """Log incoming messages"""
    user = update.effective_user
    chat = update.effective_chat
    
    log_data = {
        'user_id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'chat_id': chat.id,
        'chat_type': chat.type,
        'text': update.message.text if update.message else None,
        'command': command,
        'timestamp': datetime.now().isoformat()
    }
    
    logger.info(f"📝 Message: {json.dumps(log_data, ensure_ascii=False)}")
    bot_stats['message_count'] += 1
    bot_stats['users'].add(user.id)
    
    if command == 'start':
        bot_stats['start_count'] += 1

# ==================== BOT COMMANDS ====================
def start(update, context):
    """Handle /start command"""
    log_message(update, 'start')
    user = update.effective_user
    
    welcome_text = (
        f"👋 *ברוך הבא {user.first_name}!*\n\n"
        f"🤖 *פקודות זמינות:*\n"
        f"/start - הודעה זו\n"
        f"/help - רשימת פקודות\n"
        f"/id - הצג את ה-ID שלך\n"
        f"/info - מידע על הבוט\n"
    )
    
    if is_admin(user.id):
        welcome_text += "\n👑 *פקודות מנהל:*\n/admin - לוח בקרה\n"
    
    update.message.reply_text(welcome_text, parse_mode='Markdown')

def help_command(update, context):
    """Handle /help command"""
    log_message(update, 'help')
    
    help_text = (
        "📚 *רשימת פקודות מלאה:*\n\n"
        "🔹 *פקודות בסיסיות:*\n"
        "/start - התחל שיחה\n"
        "/help - הצג הודעה זו\n"
        "/id - הצג את ה-ID שלך\n"
        "/info - מידע על הבוט\n\n"
        "📝 *פעולות:*\n"
        "כל הודעה שתשלח - אחזיר אותה אליך\n\n"
        "💡 *טיפ:* השתמש ב-Markdown לטקסט מעוצב\n"
        "*מודגש* `קוד` _נטוי_"
    )
    
    update.message.reply_text(help_text, parse_mode='Markdown')

def show_id(update, context):
    """Handle /id command"""
    log_message(update, 'id')
    user = update.effective_user
    chat = update.effective_chat
    
    id_text = (
        f"👤 *מידע זיהוי:*\n\n"
        f"• *שם:* {user.first_name or 'ללא שם'}\n"
        f"• *Username:* @{user.username or 'ללא'}\n"
        f"• *User ID:* `{user.id}`\n"
        f"• *Chat ID:* `{chat.id}`\n"
        f"• *סוג צ'אט:* {chat.type}\n"
    )
    
    if is_admin(user.id):
        id_text += f"\n✅ *סטטוס:* מנהל"
    
    update.message.reply_text(id_text, parse_mode='Markdown')

def bot_info(update, context):
    """Handle /info command"""
    log_message(update, 'info')
    
    uptime = datetime.now() - datetime.fromisoformat(bot_stats['start_time'])
    hours, remainder = divmod(uptime.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    info_text = (
        f"📊 *סטטיסטיקות בוט:*\n\n"
        f"• ⏱️ *זמן פעילות:* {int(hours)}h {int(minutes)}m {int(seconds)}s\n"
        f"• 📨 *הודעות שקיבל:* {bot_stats['message_count']}\n"
        f"• 👥 *משתמשים ייחודיים:* {len(bot_stats['users'])}\n"
        f"• 🚀 *פקודות /start:* {bot_stats['start_count']}\n"
        f"• 🔗 *Webhook:* {'פעיל ✅' if WEBHOOK_URL else 'לא מוגדר'}\n"
        f"• 🏗️ *פלטפורמה:* Railway\n"
    )
    
    update.message.reply_text(info_text, parse_mode='Markdown')

def admin_panel(update, context):
    """Handle /admin command - Admin only"""
    user = update.effective_user
    
    if not is_admin(user.id):
        update.message.reply_text("❌ *גישה נדחית!* רק מנהל יכול להשתמש בפקודה זו.", parse_mode='Markdown')
        return
    
    log_message(update, 'admin')
    
    admin_text = (
        f"👑 *לוח בקרה למנהל*\n\n"
        f"*מנהל:* {user.first_name} (ID: `{user.id}`)\n\n"
        f"📊 *סטטיסטיקות:*\n"
        f"```json\n{json.dumps(bot_stats, default=str, indent=2)}\n```\n\n"
        f"⚙️ *פקודות מנהל:*\n"
        f"/stats - סטטיסטיקות מפורטות\n"
        f"/broadcast - שליחת הודעה לכולם\n"
        f"/restart - אתחול בוט (בפיתוח)\n"
    )
    
    update.message.reply_text(admin_text, parse_mode='Markdown')

def echo(update, context):
    """Echo user messages"""
    log_message(update, 'echo')
    text = update.message.text
    
    # Simple response with Markdown formatting
    response = f"📝 *אתה כתבת:*\n`{text}`"
    update.message.reply_text(response, parse_mode='Markdown')

def unknown(update, context):
    """Handle unknown commands"""
    log_message(update, 'unknown')
    update.message.reply_text(
        "❓ *פקודה לא מזוהה*\n"
        "השתמש ב /help כדי לראות את רשימת הפקודות.",
        parse_mode='Markdown'
    )

# ==================== SETUP HANDLERS ====================
# Command handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("help", help_command))
dispatcher.add_handler(CommandHandler("id", show_id))
dispatcher.add_handler(CommandHandler("info", bot_info))
dispatcher.add_handler(CommandHandler("admin", admin_panel))

# Message handler
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, echo))

# Unknown command handler (must be last)
dispatcher.add_handler(MessageHandler(Filters.command, unknown))

# ==================== FLASK ROUTES ====================
@app.route('/')
def home():
    """Home page"""
    return jsonify({
        "status": "online",
        "service": "telegram-bot",
        "stats": {
            "uptime": bot_stats['start_time'],
            "messages": bot_stats['message_count'],
            "unique_users": len(bot_stats['users']),
            "starts": bot_stats['start_count']
        },
        "webhook": WEBHOOK_URL if WEBHOOK_URL else "not_configured",
        "admin_configured": bool(ADMIN_USER_ID)
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook endpoint"""
    if WEBHOOK_SECRET:
        secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
        if secret != WEBHOOK_SECRET:
            logger.warning("Unauthorized webhook attempt")
            return 'Unauthorized', 403
    
    try:
        data = request.get_json()
        
        # Log webhook request
        if 'message' in data:
            msg = data['message']
            logger.info(f"📨 Webhook: {msg.get('text', '')[:50]}...")
        
        update = Update.de_json(data, bot)
        dispatcher.process_update(update)
        
        return 'OK', 200
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return 'Error', 500

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "bot": "running",
        "stats": bot_stats['message_count']
    })

@app.route('/admin/stats')
def admin_stats():
    """Admin statistics endpoint"""
    # Simple auth for web endpoint
    auth = request.args.get('auth')
    if auth != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 403
    
    return jsonify({
        "stats": bot_stats,
        "users_count": len(bot_stats['users']),
        "uptime": bot_stats['start_time'],
        "current_time": datetime.now().isoformat()
    })

# ==================== INITIALIZATION ====================
def setup_webhook():
    """Setup webhook if URL is provided"""
    if WEBHOOK_URL:
        try:
            bot.set_webhook(url=WEBHOOK_URL)
            logger.info(f"✅ Webhook configured: {WEBHOOK_URL}")
        except Exception as e:
            logger.warning(f"⚠️ Webhook setup failed: {e}")

if __name__ == '__main__':
    logger.info("🚀 Starting Telegram Bot")
    
    # Setup webhook
    setup_webhook()
    
    # Log startup info
    logger.info(f"🤖 Bot: @{bot.get_me().username}")
    logger.info(f"👑 Admin ID: {ADMIN_USER_ID or 'Not configured'}")
    logger.info(f"🌐 Flask starting on port {PORT}")
    
    # Start Flask
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
