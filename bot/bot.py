import os
import logging
import json
import time
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

# Storage files
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")
BROADCASTS_FILE = os.path.join(DATA_DIR, "broadcasts.json")

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# ==================== STORAGE FUNCTIONS ====================
def load_json(filepath, default=None):
    """Load JSON file, return default if file doesn't exist"""
    if default is None:
        default = {}
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {filepath}: {e}")
    return default

def save_json(filepath, data):
    """Save data to JSON file"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving {filepath}: {e}")
        return False

# Load existing data
users_db = load_json(USERS_FILE, [])
messages_db = load_json(MESSAGES_FILE, [])
broadcasts_db = load_json(BROADCASTS_FILE, [])

# Simple stats tracking in memory
bot_stats = {
    'start_count': 0,
    'message_count': 0,
    'users': set(),
    'start_time': datetime.now().isoformat(),
    'last_update': None
}

# Load users into memory
for user in users_db:
    if 'user_id' in user:
        bot_stats['users'].add(user['user_id'])
        bot_stats['message_count'] += user.get('message_count', 0)
        if user.get('first_seen'):
            bot_stats['start_count'] += 1

# ==================== HELPER FUNCTIONS ====================
def is_admin(user_id):
    """Check if user is admin"""
    return ADMIN_USER_ID and str(user_id) == ADMIN_USER_ID

def get_or_create_user(user_data):
    """Get existing user or create new one"""
    user_id = user_data['id']
    
    for user in users_db:
        if user['user_id'] == user_id:
            # Update user info
            user.update({
                'username': user_data.get('username'),
                'first_name': user_data.get('first_name'),
                'last_name': user_data.get('last_name'),
                'last_seen': datetime.now().isoformat(),
                'message_count': user.get('message_count', 0) + 1
            })
            save_json(USERS_FILE, users_db)
            return user
    
    # Create new user
    new_user = {
        'user_id': user_id,
        'username': user_data.get('username'),
        'first_name': user_data.get('first_name'),
        'last_name': user_data.get('last_name'),
        'first_seen': datetime.now().isoformat(),
        'last_seen': datetime.now().isoformat(),
        'message_count': 1,
        'is_admin': is_admin(user_id)
    }
    users_db.append(new_user)
    save_json(USERS_FILE, users_db)
    return new_user

def log_message(update, command=None):
    """Log incoming messages to database"""
    user = update.effective_user
    chat = update.effective_chat
    
    # Update or create user
    user_data = {
        'id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name
    }
    get_or_create_user(user_data)
    
    # Create message log
    message_log = {
        'message_id': update.message.message_id if update.message else None,
        'user_id': user.id,
        'chat_id': chat.id,
        'chat_type': chat.type,
        'text': update.message.text if update.message else None,
        'command': command,
        'timestamp': datetime.now().isoformat()
    }
    
    messages_db.append(message_log)
    if len(messages_db) > 1000:  # Keep only last 1000 messages
        messages_db.pop(0)
    save_json(MESSAGES_FILE, messages_db)
    
    # Update memory stats
    bot_stats['message_count'] += 1
    bot_stats['users'].add(user.id)
    bot_stats['last_update'] = datetime.now().isoformat()
    
    if command == 'start':
        bot_stats['start_count'] += 1
    
    logger.info(f"📝 Message from {user.first_name}: {update.message.text[:50] if update.message else 'No text'}")

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
        f"/ping - בדיקת חיים\n"
    )
    
    if is_admin(user.id):
        welcome_text += "\n👑 *פקודות מנהל:*\n/admin - לוח בקרה\n/stats - סטטיסטיקות\n/broadcast - שידור הודעה\n"
    
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
        "/info - מידע על הבוט\n"
        "/ping - בדיקת חיים\n\n"
        "👑 *פקודות מנהל:*\n"
        "/admin - לוח בקרה (מנהל בלבד)\n"
        "/stats - סטטיסטיקות (מנהל בלבד)\n"
        "/broadcast - שידור לכולם (מנהל בלבד)\n\n"
        "💡 *טיפים:*\n"
        "• השתמש ב-Markdown לעיצוב\n"
        "• *מודגש* `קוד` _נטוי_\n"
        "• שורה חדשה - רווח כפול"
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
        f"• 💾 *הודעות שמורות:* {len(messages_db)}\n"
        f"• 🔗 *Webhook:* {'פעיל ✅' if WEBHOOK_URL else 'לא מוגדר'}\n"
        f"• 🏗️ *פלטפורמה:* Railway\n"
    )
    
    update.message.reply_text(info_text, parse_mode='Markdown')

def ping(update, context):
    """Handle /ping command - quick response test"""
    log_message(update, 'ping')
    update.message.reply_text("🏓 *פונג!* הבוט חי ותקין.", parse_mode='Markdown')

def admin_panel(update, context):
    """Handle /admin command - Admin only"""
    user = update.effective_user
    
    if not is_admin(user.id):
        update.message.reply_text("❌ *גישה נדחית!* רק מנהל יכול להשתמש בפקודה זו.", parse_mode='Markdown')
        return
    
    log_message(update, 'admin')
    
    uptime = datetime.now() - datetime.fromisoformat(bot_stats['start_time'])
    
    admin_text = (
        f"👑 *לוח בקרה למנהל*\n\n"
        f"*מנהל:* {user.first_name} (ID: `{user.id}`)\n"
        f"*זמן פעילות:* {uptime}\n\n"
        f"📊 *סטטיסטיקות מהירות:*\n"
        f"• הודעות: {bot_stats['message_count']}\n"
        f"• משתמשים: {len(bot_stats['users'])}\n"
        f"• התחלות: {bot_stats['start_count']}\n"
        f"• שידורים: {len(broadcasts_db)}\n\n"
        f"⚙️ *פקודות מנהל:*\n"
        "/stats - סטטיסטיקות מפורטות\n"
        "/broadcast - שליחת הודעה לכולם\n"
        "/export - ייצוא נתונים (בפיתוח)\n"
    )
    
    update.message.reply_text(admin_text, parse_mode='Markdown')

def admin_stats(update, context):
    """Handle /stats command - Detailed stats for admin"""
    user = update.effective_user
    
    if not is_admin(user.id):
        update.message.reply_text("❌ *גישה נדחית!*", parse_mode='Markdown')
        return
    
    log_message(update, 'stats')
    
    # Calculate uptime
    start_time = datetime.fromisoformat(bot_stats['start_time'])
    uptime = datetime.now() - start_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Get active users (last 7 days)
    week_ago = datetime.now().timestamp() - (7 * 24 * 3600)
    active_users = []
    for user_record in users_db:
        last_seen = datetime.fromisoformat(user_record.get('last_seen', start_time.isoformat()))
        if last_seen.timestamp() > week_ago:
            active_users.append(user_record['user_id'])
    
    stats_text = (
        f"📈 *סטטיסטיקות מפורטות*\n\n"
        f"*מידע כללי:*\n"
        f"• התחלה: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"• זמן פעילות: {days} ימים, {hours} שעות, {minutes} דקות\n"
        f"• אחרון עדכון: {bot_stats['last_update'] or 'אין'}\n\n"
        f"*פעילות:*\n"
        f"• הודעות שקיבל: {bot_stats['message_count']}\n"
        f"• פקודות /start: {bot_stats['start_count']}\n"
        f"• משתמשים ייחודיים: {len(bot_stats['users'])}\n"
        f"• משתמשים פעילים (7 ימים): {len(active_users)}\n"
        f"• הודעות שמורות: {len(messages_db)}\n\n"
        f"*שידורים אחרונים:*\n"
    )
    
    # Add broadcast history
    if broadcasts_db:
        for i, broadcast in enumerate(broadcasts_db[-3:], 1):
            timestamp = datetime.fromisoformat(broadcast['timestamp']).strftime('%d/%m %H:%M')
            stats_text += f"{i}. {broadcast['text'][:30]}... ({timestamp})\n"
    else:
        stats_text += "אין שידורים עדיין\n"
    
    stats_text += f"\n*Webhook:* {WEBHOOK_URL or 'לא מוגדר'}"
    
    update.message.reply_text(stats_text, parse_mode='Markdown')

def broadcast_command(update, context):
    """Handle /broadcast command - Send message to all users"""
    user = update.effective_user
    
    if not is_admin(user.id):
        update.message.reply_text("❌ *גישה נדחית!* רק מנהל יכול להשתמש בפקודה זו.", parse_mode='Markdown')
        return
    
    # Get broadcast message from command arguments
    if not context.args:
        update.message.reply_text(
            "❌ *שימוש:* /broadcast <הודעה>\n\n"
            "*דוגמה:*\n"
            "/broadcast שלום לכולם! זו הודעה חשובה.\n\n"
            "⚠️ *הערה:* ההודעה תישלח לכל המשתמשים שהשתמשו בבוט.",
            parse_mode='Markdown'
        )
        return
    
    message = ' '.join(context.args)
    log_message(update, 'broadcast')
    
    # Send confirmation to admin
    update.message.reply_text(
        f"📢 *מתחיל שידור לכולם...*\n\n"
        f"*הודעה:* {message}\n"
        f"*מספר נמענים:* {len(users_db)}\n"
        f"⏳ שולח...",
        parse_mode='Markdown'
    )
    
    # Record broadcast
    broadcast_record = {
        'id': len(broadcasts_db) + 1,
        'admin_id': user.id,
        'admin_name': user.first_name,
        'text': message,
        'timestamp': datetime.now().isoformat(),
        'sent_to': 0,
        'failed': 0
    }
    
    # Send to all users
    sent_count = 0
    failed_count = 0
    
    for user_record in users_db:
        try:
            # Don't send to self
            if user_record['user_id'] == user.id:
                continue
                
            bot.send_message(
                chat_id=user_record['user_id'],
                text=f"📢 *הודעה מהמנהל:*\n\n{message}",
                parse_mode='Markdown'
            )
            sent_count += 1
            
            # Small delay to avoid rate limits
            time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Failed to send broadcast to {user_record['user_id']}: {e}")
            failed_count += 1
    
    # Update broadcast record
    broadcast_record['sent_to'] = sent_count
    broadcast_record['failed'] = failed_count
    broadcasts_db.append(broadcast_record)
    save_json(BROADCASTS_FILE, broadcasts_db)
    
    # Send final report
    update.message.reply_text(
        f"✅ *שידור הושלם!*\n\n"
        f"📊 *תוצאות:*\n"
        f"• ✅ נשלח בהצלחה: {sent_count}\n"
        f"• ❌ נכשל: {failed_count}\n"
        f"• 👥 סה״כ נמענים: {len(users_db)}\n"
        f"• 📝 *הודעה:* {message[:50]}...",
        parse_mode='Markdown'
    )

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
dispatcher.add_handler(CommandHandler("ping", ping))
dispatcher.add_handler(CommandHandler("admin", admin_panel))
dispatcher.add_handler(CommandHandler("stats", admin_stats))
dispatcher.add_handler(CommandHandler("broadcast", broadcast_command, pass_args=True))

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
        "bot": "@" + (bot.get_me().username if bot.get_me() else "unknown"),
        "stats": {
            "uptime": bot_stats['start_time'],
            "messages": bot_stats['message_count'],
            "unique_users": len(bot_stats['users']),
            "starts": bot_stats['start_count'],
            "stored_messages": len(messages_db),
            "stored_users": len(users_db),
            "broadcasts": len(broadcasts_db)
        },
        "webhook": WEBHOOK_URL if WEBHOOK_URL else "not_configured",
        "admin_configured": bool(ADMIN_USER_ID),
        "data_storage": "active"
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
        "stats": {
            "messages": bot_stats['message_count'],
            "users": len(bot_stats['users']),
            "uptime": bot_stats['start_time']
        },
        "storage": {
            "users": len(users_db),
            "messages": len(messages_db),
            "broadcasts": len(broadcasts_db)
        }
    })

@app.route('/admin/data', methods=['GET'])
def admin_data():
    """Admin data endpoint (requires secret)"""
    auth = request.args.get('auth')
    if auth != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 403
    
    return jsonify({
        "users": users_db,
        "messages_count": len(messages_db),
        "broadcasts": broadcasts_db,
        "stats": bot_stats
    })

@app.route('/admin/backup', methods=['GET'])
def admin_backup():
    """Create backup of all data"""
    auth = request.args.get('auth')
    if auth != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 403
    
    backup_data = {
        "timestamp": datetime.now().isoformat(),
        "users": users_db,
        "messages": messages_db,
        "broadcasts": broadcasts_db,
        "stats": bot_stats
    }
    
    return jsonify(backup_data)

# ==================== INITIALIZATION ====================
def setup_webhook():
    """Setup webhook if URL is provided"""
    if WEBHOOK_URL:
        try:
            # Ensure webhook URL ends with /webhook
            webhook_url = WEBHOOK_URL.rstrip('/') + '/webhook'
            bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Webhook configured: {webhook_url}")
        except Exception as e:
            logger.warning(f"⚠️ Webhook setup failed: {e}")

if __name__ == '__main__':
    logger.info("🚀 Starting Telegram Bot")
    
    # Setup webhook
    setup_webhook()
    
    # Log startup info
    logger.info(f"🤖 Bot: @{bot.get_me().username}")
    logger.info(f"👑 Admin ID: {ADMIN_USER_ID or 'Not configured'}")
    logger.info(f"💾 Storage: {len(users_db)} users, {len(messages_db)} messages loaded")
    logger.info(f"🌐 Flask starting on port {PORT}")
    
    # Start Flask
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
