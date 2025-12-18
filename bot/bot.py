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

# Bot initialization with better error handling
try:
    bot = Bot(token=TOKEN, request_timeout=30)
    dispatcher = Dispatcher(bot, None, workers=2)
except Exception as e:
    logger.error(f"Failed to initialize bot: {e}")
    raise

# Simple stats tracking
bot_stats = {
    'start_count': 0,
    'message_count': 0,
    'users': set(),
    'start_time': datetime.now().isoformat(),
    'last_update': None,
    'errors': 0
}

# Broadcast message storage (simple in-memory)
broadcast_messages = []

# ==================== HELPER FUNCTIONS ====================
def is_admin(user_id):
    """Check if user is admin"""
    return ADMIN_USER_ID and str(user_id) == ADMIN_USER_ID

def safe_send_message(chat_id, text, parse_mode=None):
    """Safely send message with error handling"""
    try:
        bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            timeout=20
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send message to {chat_id}: {e}")
        bot_stats['errors'] += 1
        return False

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
    bot_stats['last_update'] = datetime.now().isoformat()
    
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
        f"/ping - בדיקת חיים\n"
        f"/echo <טקסט> - הד בחזרה\n"
    )
    
    if is_admin(user.id):
        welcome_text += "\n👑 *פקודות מנהל:*\n/admin - לוח בקרה\n/stats - סטטיסטיקות\n/broadcast - שידור הודעה\n"
    
    # Use safe send
    safe_send_message(update.effective_chat.id, welcome_text, parse_mode='Markdown')

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
        "/ping - בדיקת חיים\n"
        "/echo <טקסט> - הדבקת טקסט\n\n"
        "👑 *פקודות מנהל:*\n"
        "/admin - לוח בקרה (מנהל בלבד)\n"
        "/stats - סטטיסטיקות (מנהל בלבד)\n"
        "/broadcast - שידור לכולם (מנהל בלבד)\n\n"
        "💡 *טיפים:*\n"
        "• השתמש ב-Markdown לעיצוב\n"
        "• *מודגש* `קוד` _נטוי_\n"
        "• שורה חדשה - רווח כפול\n"
        "• /echo שלום עולם - יחזיר 'שלום עולם'"
    )
    
    safe_send_message(update.effective_chat.id, help_text, parse_mode='Markdown')

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
    
    safe_send_message(update.effective_chat.id, id_text, parse_mode='Markdown')

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
        f"• ❌ *שגיאות שליחה:* {bot_stats['errors']}\n"
        f"• 🔗 *Webhook:* {'פעיל ✅' if WEBHOOK_URL else 'לא מוגדר'}\n"
        f"• 🏗️ *פלטפורמה:* Railway\n"
    )
    
    safe_send_message(update.effective_chat.id, info_text, parse_mode='Markdown')

def ping(update, context):
    """Handle /ping command - quick response test"""
    log_message(update, 'ping')
    safe_send_message(update.effective_chat.id, "🏓 *פונג!* הבוט חי ותקין.", parse_mode='Markdown')

def echo_command(update, context):
    """Handle /echo command - echo with text"""
    log_message(update, 'echo')
    
    # Get text after command
    text = ' '.join(context.args) if context.args else ''
    
    if not text:
        response = "❌ *שימוש:* /echo <טקסט>\nלדוגמה: /echo שלום עולם"
    else:
        response = f"📣 *הד:*\n{text}"
    
    safe_send_message(update.effective_chat.id, response, parse_mode='Markdown')

def admin_panel(update, context):
    """Handle /admin command - Admin only"""
    user = update.effective_user
    
    if not is_admin(user.id):
        safe_send_message(update.effective_chat.id, "❌ *גישה נדחית!* רק מנהל יכול להשתמש בפקודה זו.", parse_mode='Markdown')
        return
    
    log_message(update, 'admin')
    
    uptime = datetime.now() - datetime.fromisoformat(bot_stats['start_time'])
    hours, remainder = divmod(uptime.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    admin_text = (
        f"👑 *לוח בקרה למנהל*\n\n"
        f"*מנהל:* {user.first_name} (ID: `{user.id}`)\n"
        f"*זמן פעילות:* {int(hours)}h {int(minutes)}m {int(seconds)}s\n\n"
        f"📊 *סטטיסטיקות מהירות:*\n"
        f"• הודעות: {bot_stats['message_count']}\n"
        f"• משתמשים: {len(bot_stats['users'])}\n"
        f"• התחלות: {bot_stats['start_count']}\n"
        f"• שגיאות: {bot_stats['errors']}\n\n"
        f"⚙️ *פקודות מנהל:*\n"
        "/stats - סטטיסטיקות מפורטות\n"
        "/broadcast <הודעה> - שידור לכולם\n"
        "/echo <טקסט> - בדיקת שליחה\n"
    )
    
    safe_send_message(update.effective_chat.id, admin_text, parse_mode='Markdown')

def admin_stats(update, context):
    """Handle /stats command - Detailed stats for admin"""
    user = update.effective_user
    
    if not is_admin(user.id):
        safe_send_message(update.effective_chat.id, "❌ *גישה נדחית!*", parse_mode='Markdown')
        return
    
    log_message(update, 'stats')
    
    # Calculate uptime
    start_time = datetime.fromisoformat(bot_stats['start_time'])
    uptime = datetime.now() - start_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Get list of users (first 10)
    users_list = list(bot_stats['users'])[:10]
    
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
        f"• שגיאות שליחה: {bot_stats['errors']}\n\n"
        f"*שידורים אחרונים:*\n"
    )
    
    # Add broadcast history
    if broadcast_messages:
        for i, msg in enumerate(broadcast_messages[-5:], 1):
            stats_text += f"{i}. {msg['text'][:30]}... ({msg['timestamp']})\n"
    else:
        stats_text += "אין שידורים עדיין\n"
    
    stats_text += f"\n*משתמשים אחרונים (10):*\n"
    
    # Add users list
    for i, user_id in enumerate(users_list, 1):
        stats_text += f"{i}. `{user_id}`\n"
    
    if len(bot_stats['users']) > 10:
        stats_text += f"... ועוד {len(bot_stats['users']) - 10} משתמשים\n"
    
    stats_text += f"\n*Webhook:* {WEBHOOK_URL or 'לא מוגדר'}"
    
    safe_send_message(update.effective_chat.id, stats_text, parse_mode='Markdown')

def broadcast_command(update, context):
    """Handle /broadcast command - Send message to all users"""
    user = update.effective_user
    
    if not is_admin(user.id):
        safe_send_message(update.effective_chat.id, "❌ *גישה נדחית!* רק מנהל יכול להשתמש בפקודה זו.", parse_mode='Markdown')
        return
    
    # Get broadcast message
    message = ' '.join(context.args) if context.args else ''
    
    if not message:
        safe_send_message(
            update.effective_chat.id,
            "❌ *שימוש:* /broadcast <הודעה>\n\n"
            "*דוגמה:*\n"
            "/broadcast הודעה חשובה לכולם!\n\n"
            "⚠️ *אזהרה:* ההודעה תישלח לכל המשתמשים שהשתמשו בבוט.",
            parse_mode='Markdown'
        )
        return
    
    log_message(update, 'broadcast')
    
    # Store broadcast message
    broadcast_data = {
        'text': message,
        'from_admin': user.id,
        'timestamp': datetime.now().isoformat(),
        'sent_to': 0,
        'failed': 0
    }
    
    # Send to admin first
    safe_send_message(
        update.effective_chat.id,
        f"📢 *מתחיל שידור לכולם:*\n\n{message}\n\n"
        f"👥 *משתמשים:* {len(bot_stats['users'])}\n"
        f"⏳ *שולח...*",
        parse_mode='Markdown'
    )
    
    # Send to all users
    success_count = 0
    fail_count = 0
    
    for user_id in bot_stats['users']:
        if str(user_id) == ADMIN_USER_ID:
            continue  # Skip admin
        
        if safe_send_message(user_id, f"📢 *הודעה מהמנהל:*\n\n{message}", parse_mode='Markdown'):
            success_count += 1
        else:
            fail_count += 1
        
        # Small delay to avoid rate limits
        time.sleep(0.1)
    
    # Update broadcast data
    broadcast_data['sent_to'] = success_count
    broadcast_data['failed'] = fail_count
    broadcast_messages.append(broadcast_data)
    
    # Keep only last 20 broadcasts
    if len(broadcast_messages) > 20:
        broadcast_messages.pop(0)
    
    # Send report to admin
    report_text = (
        f"✅ *שידור הושלם!*\n\n"
        f"📝 *הודעה:* {message[:50]}...\n\n"
        f"📊 *תוצאות:*\n"
        f"• ✅ נשלח בהצלחה: {success_count}\n"
        f"• ❌ נכשל: {fail_count}\n"
        f"• 👥 סה״כ נמענים: {len(bot_stats['users'])}\n"
        f"• ⏱️ זמן: {datetime.now().strftime('%H:%M:%S')}"
    )
    
    safe_send_message(update.effective_chat.id, report_text, parse_mode='Markdown')

def echo(update, context):
    """Echo user messages (not commands)"""
    log_message(update, 'echo')
    text = update.message.text
    
    # Simple response with Markdown formatting
    response = f"📝 *אתה כתבת:*\n`{text}`"
    safe_send_message(update.effective_chat.id, response, parse_mode='Markdown')

def unknown(update, context):
    """Handle unknown commands"""
    log_message(update, 'unknown')
    safe_send_message(
        update.effective_chat.id,
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
dispatcher.add_handler(CommandHandler("echo", echo_command, pass_args=True))
dispatcher.add_handler(CommandHandler("admin", admin_panel))
dispatcher.add_handler(CommandHandler("stats", admin_stats))
dispatcher.add_handler(CommandHandler("broadcast", broadcast_command, pass_args=True))

# Message handler for non-command text
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
            "errors": bot_stats['errors']
        },
        "webhook": WEBHOOK_URL if WEBHOOK_URL else "not_configured",
        "admin_configured": bool(ADMIN_USER_ID),
        "broadcasts_sent": len(broadcast_messages)
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook endpoint"""
    # Debug: Log the request
    logger.info(f"🌐 Webhook received from {request.remote_addr}")
    
    if WEBHOOK_SECRET:
        secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
        if secret != WEBHOOK_SECRET:
            logger.warning(f"Unauthorized webhook attempt. Expected: {WEBHOOK_SECRET}, Got: {secret}")
            return 'Unauthorized', 403
    
    try:
        data = request.get_json()
        
        # Log webhook request
        if 'message' in data and 'text' in data['message']:
            text = data['message']['text']
            user_id = data['message']['from']['id']
            logger.info(f"📨 Webhook: User {user_id} sent: '{text}'")
        else:
            logger.info(f"📨 Webhook: Update received (no text)")
        
        update = Update.de_json(data, bot)
        dispatcher.process_update(update)
        
        return 'OK', 200
    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        bot_stats['errors'] += 1
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
            "uptime": bot_stats['start_time'],
            "errors": bot_stats['errors']
        }
    })

@app.route('/admin/web', methods=['GET'])
def admin_web():
    """Web admin panel (simple)"""
    auth = request.args.get('auth')
    if auth != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 403
    
    return jsonify({
        "stats": bot_stats,
        "users_count": len(bot_stats['users']),
        "users_list": list(bot_stats['users'])[:50],
        "uptime": bot_stats['start_time'],
        "current_time": datetime.now().isoformat(),
        "webhook_url": WEBHOOK_URL,
        "broadcasts": broadcast_messages[-10:] if broadcast_messages else []
    })

# ==================== INITIALIZATION ====================
def setup_webhook():
    """Setup webhook if URL is provided"""
    if WEBHOOK_URL and not WEBHOOK_URL.endswith('/webhook'):
        corrected_url = WEBHOOK_URL.rstrip('/') + '/webhook'
    else:
        corrected_url = WEBHOOK_URL
    
    if corrected_url:
        try:
            # Try to set webhook with the correct URL
            bot.set_webhook(url=corrected_url)
            logger.info(f"✅ Webhook configured: {corrected_url}")
            
            # Also log the current webhook info for debugging
            try:
                info = bot.get_webhook_info()
                logger.info(f"📋 Webhook info: {info.url}, Pending: {info.pending_update_count}")
            except:
                pass
                
        except Exception as e:
            logger.warning(f"⚠️ Webhook setup failed: {e}")

if __name__ == '__main__':
    logger.info("🚀 Starting Telegram Bot")
    
    # Log bot info
    try:
        bot_info = bot.get_me()
        logger.info(f"🤖 Bot: @{bot_info.username} (ID: {bot_info.id})")
    except Exception as e:
        logger.error(f"Failed to get bot info: {e}")
    
    logger.info(f"👑 Admin ID: {ADMIN_USER_ID or 'Not configured'}")
    logger.info(f"🔐 Webhook Secret: {'Set' if WEBHOOK_SECRET else 'Not set'}")
    logger.info(f"🌐 Webhook URL: {WEBHOOK_URL or 'None'}")
    
    # Setup webhook
    setup_webhook()
    
    logger.info(f"🌐 Flask starting on port {PORT}")
    
    # Start Flask
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
