import os
import logging
import json
import re
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from telegram import Bot, Update, ParseMode, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram.utils.helpers import escape_markdown

# ==================== CONFIGURATION ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Environment variables
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET')
ADMIN_USER_ID = os.environ.get('ADMIN_USER_ID', '').strip()
BOT_USERNAME = None  # Will be set dynamically
PORT = int(os.environ.get('PORT', 8080))

# Validation
if not TOKEN:
    raise ValueError("❌ TELEGRAM_BOT_TOKEN is required!")

# Bot initialization
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, workers=2)

# Get bot info dynamically
try:
    bot_info = bot.get_me()
    BOT_USERNAME = bot_info.username
    BOT_ID = bot_info.id
    BOT_NAME = bot_info.first_name
    logger.info(f"🤖 Bot loaded: @{BOT_USERNAME} (ID: {BOT_ID}, Name: {BOT_NAME})")
except Exception as e:
    logger.error(f"Failed to get bot info: {e}")
    # Fallback to environment variables
    BOT_USERNAME = os.environ.get('BOT_USERNAME', 'unknown_bot')
    BOT_ID = os.environ.get('BOT_ID', 'unknown')
    BOT_NAME = os.environ.get('BOT_NAME', 'Telegram Bot')

# Storage files
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")
BROADCASTS_FILE = os.path.join(DATA_DIR, "broadcasts.json")
GROUPS_FILE = os.path.join(DATA_DIR, "groups.json")

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
groups_db = load_json(GROUPS_FILE, [])

# Simple stats tracking in memory
bot_stats = {
    'start_count': 0,
    'message_count': 0,
    'users': set(),
    'groups': set(),
    'start_time': datetime.now().isoformat(),
    'last_update': None,
    'bot_id': BOT_ID,
    'bot_username': BOT_USERNAME
}

# Load users and groups into memory
for user in users_db:
    if 'user_id' in user:
        bot_stats['users'].add(user['user_id'])
        bot_stats['message_count'] += user.get('message_count', 0)
        if user.get('first_seen'):
            bot_stats['start_count'] += 1

for group in groups_db:
    if 'chat_id' in group:
        bot_stats['groups'].add(group['chat_id'])

# ==================== KEYBOARDS ====================
def get_main_keyboard(user_id=None):
    """Main menu keyboard"""
    keyboard = [
        [KeyboardButton("📊 סטטיסטיקות"), KeyboardButton("ℹ️ מידע על הבוט")],
        [KeyboardButton("🆔 הצג ID שלי"), KeyboardButton("🔧 תפריט מנהל")] if user_id and is_admin(user_id) else [KeyboardButton("👤 אודותיי"), KeyboardButton("📞 צור קשר")],
        [KeyboardButton("❓ עזרה"), KeyboardButton("🔄 רענן")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_admin_keyboard():
    """Admin menu keyboard"""
    keyboard = [
        [KeyboardButton("📢 שידור לכולם"), KeyboardButton("📈 סטטיסטיקות מפורטות")],
        [KeyboardButton("👥 ניהול משתמשים"), KeyboardButton("⚙️ הגדרות")],
        [KeyboardButton("🏠 לתפריט הראשי"), KeyboardButton("🔄 אתחול בוט")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_group_keyboard():
    """Group menu keyboard (for groups)"""
    keyboard = [
        [KeyboardButton(f"@{BOT_USERNAME} סטטוס"), KeyboardButton(f"@{BOT_USERNAME} מידע")],
        [KeyboardButton(f"@{BOT_USERNAME} הפקודות"), KeyboardButton(f"@{BOT_USERNAME} עזרה")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

# ==================== HELPER FUNCTIONS ====================
def is_admin(user_id):
    """Check if user is admin"""
    return ADMIN_USER_ID and str(user_id) == ADMIN_USER_ID

def should_respond(update):
    """Check if bot should respond to message (for groups)"""
    message = update.message
    if not message:
        return False
    
    # Always respond to commands
    if message.entities and any(entity.type == 'bot_command' for entity in message.entities):
        return True
    
    # Check if in private chat - always respond
    if message.chat.type == 'private':
        return True
    
    # Check if bot is mentioned in group
    if BOT_USERNAME and message.text and f"@{BOT_USERNAME}" in message.text:
        return True
    
    # Check if message is a reply to bot's message
    if message.reply_to_message and message.reply_to_message.from_user.id == BOT_ID:
        return True
    
    # For groups, only respond to specific triggers
    triggers = [f"@{BOT_USERNAME}", "בוט", "רובוט", "עזרה", "help"]
    if message.text and any(trigger in message.text.lower() for trigger in triggers):
        return True
    
    return False

def get_or_create_user(user_data, chat_type='private'):
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
                'chat_type': chat_type,
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
        'chat_type': chat_type,
        'message_count': 1,
        'is_admin': is_admin(user_id)
    }
    users_db.append(new_user)
    save_json(USERS_FILE, users_db)
    return new_user

def register_group(chat):
    """Register group in database"""
    chat_id = chat.id
    
    for group in groups_db:
        if group['chat_id'] == chat_id:
            group['last_activity'] = datetime.now().isoformat()
            group['title'] = chat.title
            save_json(GROUPS_FILE, groups_db)
            return group
    
    # Create new group record
    new_group = {
        'chat_id': chat_id,
        'title': chat.title,
        'type': chat.type,
        'first_seen': datetime.now().isoformat(),
        'last_activity': datetime.now().isoformat(),
        'member_count': chat.get_members_count() if hasattr(chat, 'get_members_count') else 0
    }
    groups_db.append(new_group)
    bot_stats['groups'].add(chat_id)
    save_json(GROUPS_FILE, groups_db)
    return new_group

def log_message(update, command=None):
    """Log incoming messages to database"""
    message = update.message
    if not message:
        return
    
    user = update.effective_user
    chat = update.effective_chat
    
    # Update or create user
    user_data = {
        'id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name
    }
    get_or_create_user(user_data, chat.type)
    
    # Register group if in group
    if chat.type in ['group', 'supergroup']:
        register_group(chat)
    
    # Create message log
    message_log = {
        'message_id': message.message_id,
        'user_id': user.id,
        'chat_id': chat.id,
        'chat_type': chat.type,
        'text': message.text,
        'command': command,
        'timestamp': datetime.now().isoformat(),
        'bot_mentioned': BOT_USERNAME and message.text and f"@{BOT_USERNAME}" in message.text
    }
    
    messages_db.append(message_log)
    if len(messages_db) > 2000:  # Keep only last 2000 messages
        messages_db.pop(0)
    save_json(MESSAGES_FILE, messages_db)
    
    # Update memory stats
    bot_stats['message_count'] += 1
    bot_stats['users'].add(user.id)
    bot_stats['last_update'] = datetime.now().isoformat()
    
    if command == 'start':
        bot_stats['start_count'] += 1
    
    logger.info(f"📝 {chat.type.capitalize()} message from {user.first_name}: {message.text[:50] if message.text else 'No text'}")

def escape_markdown_v2(text):
    """Escape special characters for MarkdownV2"""
    if not text:
        return ""
    # Escape special characters for Telegram MarkdownV2
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

# ==================== BOT COMMANDS ====================
def start(update, context):
    """Handle /start command"""
    log_message(update, 'start')
    user = update.effective_user
    chat = update.effective_chat
    
    # Different welcome for groups vs private
    if chat.type == 'private':
        welcome_text = (
            f"👋 *ברוך הבא {user.first_name}!*\n\n"
            f"🤖 *אני {BOT_NAME}, הבוט החכם שלך!*\n\n"
            f"🚀 *מה אני יכול לעשות?*\n"
            f"• ניהול קבוצות ואירועים\n"
            f"• שליחת הודעות מתוזמנות\n"
            f"• ניתוח סטטיסטיקות\n"
            f"• תקשורת עם APIs חיצוניים\n\n"
            f"📋 *השתמש בתפריט למטה או בפקודות:*\n"
            f"/help - רשימת פקודות\n"
            f"/menu - תפריט כפתורים\n"
            f"/about - מידע על הבוט\n"
            f"/botinfo - פרטים טכניים\n"
        )
        
        if is_admin(user.id):
            welcome_text += "\n👑 *גישה למנהל זוהתה!*\nהשתמש בתפריט המנהל או ב-/admin"
        
        update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_keyboard(user.id)
        )
    else:
        # Group welcome
        welcome_text = (
            f"👋 *שלום לכולם!*\n\n"
            f"🤖 *אני {BOT_NAME} כאן לעזור לכם!*\n\n"
            f"📍 *כדי להשתמש בי בקבוצה:*\n"
            f"1. הזכירו אותי עם @{BOT_USERNAME}\n"
            f"2. או השתמשו בפקודות ישירות\n"
            f"3. או לחצו על הכפתורים למטה\n\n"
            f"📌 *דוגמאות:*\n"
            f"`@{BOT_USERNAME} סטטוס`\n"
            f"`@{BOT_USERNAME} עזרה`\n"
            f"/help@{BOT_USERNAME}"
        )
        
        update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_group_keyboard()
        )

def help_command(update, context):
    """Handle /help command"""
    log_message(update, 'help')
    chat = update.effective_chat
    
    if chat.type == 'private':
        help_text = (
            "📚 *רשימת פקודות מלאה*\n\n"
            "🔹 *פקודות בסיסיות:*\n"
            "/start - הודעת פתיחה\n"
            "/help - רשימת פקודות זו\n"
            "/menu - תפריט כפתורים\n"
            "/about - מידע על הבוט\n"
            "/botinfo - פרטי הבוט (ID, שם)\n"
            "/id - הצג את ה-ID שלך\n"
            "/info - סטטיסטיקות בוט\n"
            "/ping - בדיקת חיים\n\n"
            "👑 *פקודות מנהל:*\n"
            "/admin - לוח בקרה\n"
            "/stats - סטטיסטיקות מפורטות\n"
            "/broadcast - שידור לכולם\n"
            "/users - ניהול משתמשים\n"
            "/export - ייצוא נתונים\n"
            "/restart - אתחול בוט\n\n"
            "💡 *בקבוצות:*\n"
            f"הזכירו אותי עם @{BOT_USERNAME}\n"
            "או השתמשו בפקודות ישירות\n\n"
            "⚙️ *פיתוח עתידי:*\n"
            "• אינטגרציה עם מאגרי מידע\n"
            "• הודעות מתוזמנות אוטומטיות\n"
            "• ניתוח טקסטים מתקדם\n"
            "• חיבור ל-APIs חיצוניים"
        )
    else:
        help_text = (
            f"🤖 *פקודות זמינות בקבוצה:*\n\n"
            f"📍 *הזכירו אותי עם @{BOT_USERNAME}* או השתמשו בפקודות:\n\n"
            f"`@{BOT_USERNAME} סטטוס` - מצב הבוט\n"
            f"`@{BOT_USERNAME} מידע` - מידע על הבוט\n"
            f"`@{BOT_USERNAME} עזרה` - הודעה זו\n"
            f"`@{BOT_USERNAME} id` - הצג ID\n\n"
            f"📌 *פקודות ישירות:*\n"
            f"/help@{BOT_USERNAME} - עזרה\n"
            f"/about@{BOT_USERNAME} - אודות\n"
            f"/info@{BOT_USERNAME} - סטטיסטיקות\n\n"
            f"💡 *טיפ:* השתמשו בכפתורים למטה לנוחות!"
        )
    
    try:
        update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Error sending help: {e}")
        # Fallback without markdown - more reliable
        plain_text = help_text.replace('*', '').replace('`', '').replace('_', '')
        update.message.reply_text(plain_text)

def about_command(update, context):
    """Handle /about command - Information about bot's purpose"""
    log_message(update, 'about')
    
    about_text = (
        f"🌟 *אודות {BOT_NAME}*\n\n"
        f"🤖 *מהות הבוט:*\n"
        f"בוט טלגרם חכם ומודולרי שפותח כדי לפשט תקשורת וניהול בקהילות וקבוצות.\n\n"
        f"🎯 *מטרות וייעוד עתידי:*\n"
        f"• 🤝 ניהול קהילות וקבוצות\n"
        f"• 📅 תזכורות ואירועים מתוזמנים\n"
        f"• 📊 ניתוח סטטיסטיקות ופעילות\n"
        f"• 🔗 אינטגרציה עם שירותים חיצוניים\n"
        f"• 🛠️ כלים לניהול תוכן ותקשורת\n\n"
        f"🚀 *פיתוח עתידי מתוכנן:*\n"
        f"1. מערכת ניהול אירועים\n"
        f"2. אינטגרציה עם Google Sheets/Calendar\n"
        f"3. בוט משחקים ואינטראקציה\n"
        f"4. מערכת הצבעות וסקרים\n"
        f"5. ניתוח סנטימנט וטקסט\n\n"
        f"💡 *רעיונות? הצעות?*\n"
        f"צור קשר עם המפתח: @OsifEU\n\n"
        f"📝 *גרסה:* 4.0 (בוט מתקדם)\n"
        f"🏗️ *פלטפורמה:* Railway\n"
        f"🔧 *מצב:* פעיל ובעל פיתוח"
    )
    
    update.message.reply_text(about_text, parse_mode=ParseMode.MARKDOWN)

def botinfo_command(update, context):
    """Handle /botinfo command - Show bot's own ID and info"""
    log_message(update, 'botinfo')
    
    # Get bot info fresh
    try:
        bot_me = bot.get_me()
        botinfo_text = (
            f"🔧 *פרטי הבוט הטכניים*\n\n"
            f"• 🤖 *שם הבוט:* {bot_me.first_name}\n"
            f"• 📛 *שם משתמש:* @{bot_me.username}\n"
            f"• 🆔 *ID הבוט:* `{bot_me.id}`\n"
            f"• 📝 *שם מלא:* {bot_me.full_name}\n"
            f"• 🔗 *קישור:* t.me/{bot_me.username}\n"
            f"• 📄 *סוג:* {'Bot' if bot_me.is_bot else 'User'}\n\n"
            f"📊 *סטטיסטיקות מערכת:*\n"
            f"• 🏗️ *פלטפורמה:* Railway\n"
            f"• 📁 *מאגר נתונים:* {len(users_db)} משתמשים, {len(groups_db)} קבוצות\n"
            f"• ⚙️ *גרסת קוד:* 4.0 (בוט חכם)\n"
            f"• 🔐 *מצב אבטחה:* {'מאובטח עם Webhook' if WEBHOOK_URL else 'Polling'}\n\n"
            f"💡 *שימוש ב-ID הבוט:*\n"
            f"השתמש ב-ID `{bot_me.id}` עבור:\n"
            f"• אינטגרציה עם APIs\n"
            f"• בדיקות ופיתוח\n"
            f"• קישורים ישירים"
        )
    except Exception as e:
        botinfo_text = f"❌ *שגיאה בטעינת פרטי הבוט:* {e}"
    
    update.message.reply_text(botinfo_text, parse_mode=ParseMode.MARKDOWN)

def menu_command(update, context):
    """Handle /menu command - Show interactive menu"""
    log_message(update, 'menu')
    user = update.effective_user
    
    menu_text = (
        f"📱 *תפריט ראשי - {BOT_NAME}*\n\n"
        f"🔹 *בחר אפשרות מהתפריט למטה:*\n\n"
        f"📊 *מידע וסטטיסטיקות:*\n"
        f"• סטטיסטיקות - נתוני שימוש\n"
        f"• מידע על הבוט - מהות ותכונות\n"
        f"• הצג ID שלי - פרטי זיהוי\n\n"
        f"🛠️ *כלים ופעולות:*\n"
        f"• עזרה - הדרכה ושימוש\n"
        f"• רענן - עדכון תפריט\n"
    )
    
    if is_admin(user.id):
        menu_text += f"\n👑 *תפריט מנהל:*\n• תפריט מנהל - כלי ניהול מתקדמים\n"
    
    menu_text += f"\n📍 *או השתמש בפקודות מהרשימה ב /help*"
    
    update.message.reply_text(
        menu_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard(user.id)
    )

def show_id(update, context):
    """Handle /id command"""
    log_message(update, 'id')
    user = update.effective_user
    chat = update.effective_chat
    
    id_text = (
        f"👤 *פרטי זיהוי:*\n\n"
        f"• *שמך:* {user.first_name or 'ללא שם'}\n"
        f"• *שם משתמש:* @{user.username or 'ללא'}\n"
        f"• *User ID:* `{user.id}`\n"
        f"• *Chat ID:* `{chat.id}`\n"
        f"• *סוג צ'אט:* {chat.type}\n"
        f"• *שם הבוט:* {BOT_NAME}\n"
        f"• *ID הבוט:* `{BOT_ID}`\n"
    )
    
    if is_admin(user.id):
        id_text += f"\n✅ *סטטוס:* מנהל (ID: {ADMIN_USER_ID})"
    
    update.message.reply_text(id_text, parse_mode=ParseMode.MARKDOWN)

def bot_info(update, context):
    """Handle /info command"""
    log_message(update, 'info')
    
    uptime = datetime.now() - datetime.fromisoformat(bot_stats['start_time'])
    hours, remainder = divmod(uptime.total_seconds(), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Calculate daily average
    days = uptime.days if uptime.days > 0 else 1
    daily_avg = bot_stats['message_count'] / days
    
    info_text = (
        f"📊 *סטטיסטיקות {BOT_NAME}*\n\n"
        f"• ⏱️ *זמן פעילות:* {int(hours)}h {int(minutes)}m {int(seconds)}s\n"
        f"• 📨 *הודעות שקיבל:* {bot_stats['message_count']}\n"
        f"• 📈 *ממוצע יומי:* {daily_avg:.1f} הודעות/יום\n"
        f"• 👥 *משתמשים ייחודיים:* {len(bot_stats['users'])}\n"
        f"• 👥 *קבוצות פעילות:* {len(bot_stats['groups'])}\n"
        f"• 🚀 *פקודות /start:* {bot_stats['start_count']}\n"
        f"• 💾 *הודעות שמורות:* {len(messages_db)}\n"
        f"• 🤖 *שם הבוט:* {BOT_NAME}\n"
        f"• 🆔 *ID הבוט:* `{BOT_ID}`\n"
        f"• 🔗 *Webhook:* {'פעיל ✅' if WEBHOOK_URL else 'לא מוגדר'}\n"
        f"• 🏗️ *פלטפורמה:* Railway\n"
        f"• 📅 *התחלה:* {datetime.fromisoformat(bot_stats['start_time']).strftime('%d/%m/%Y %H:%M')}"
    )
    
    update.message.reply_text(info_text, parse_mode=ParseMode.MARKDOWN)

def ping(update, context):
    """Handle /ping command - quick response test"""
    log_message(update, 'ping')
    
    # Calculate response time
    start_time = time.time()
    message = update.message.reply_text("🏓 *מחכה לתגובת שרת...*", parse_mode=ParseMode.MARKDOWN)
    response_time = (time.time() - start_time) * 1000  # in milliseconds
    
    ping_text = (
        f"🏓 *פונג!*\n\n"
        f"✅ *הבוט חי ותקין*\n\n"
        f"📊 *ביצועים:*\n"
        f"• ⚡ *זמן תגובה:* {response_time:.0f}ms\n"
        f"• 🖥️ *מעבדים:* {dispatcher.workers}\n"
        f"• 💾 *זיכרון משתמשים:* {len(users_db)}\n"
        f"• 📡 *סטטוס:* {'Webhook פעיל' if WEBHOOK_URL else 'Polling'}\n\n"
        f"🤖 *פרטי מערכת:*\n"
        f"• שם: {BOT_NAME}\n"
        f"• ID: `{BOT_ID}`\n"
        f"• משתמש: @{BOT_USERNAME}"
    )
    
    message.edit_text(ping_text, parse_mode=ParseMode.MARKDOWN)

def admin_panel(update, context):
    """Handle /admin command - Admin only"""
    user = update.effective_user
    
    if not is_admin(user.id):
        update.message.reply_text("❌ *גישה נדחית!* רק מנהל יכול להשתמש בפקודה זו.", parse_mode=ParseMode.MARKDOWN)
        return
    
    log_message(update, 'admin')
    
    uptime = datetime.now() - datetime.fromisoformat(bot_stats['start_time'])
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    
    admin_text = (
        f"👑 *לוח בקרה למנהל - {BOT_NAME}*\n\n"
        f"*מנהל:* {user.first_name} (ID: `{user.id}`)\n"
        f"*בוט:* {BOT_NAME} (ID: `{BOT_ID}`)\n"
        f"*זמן פעילות:* {days} ימים, {hours} שעות, {minutes} דקות\n\n"
        f"📊 *סטטיסטיקות מהירות:*\n"
        f"• 📨 הודעות: {bot_stats['message_count']}\n"
        f"• 👥 משתמשים: {len(bot_stats['users'])}\n"
        f"• 👥 קבוצות: {len(bot_stats['groups'])}\n"
        f"• 🚀 התחלות: {bot_stats['start_count']}\n"
        f"• 📢 שידורים: {len(broadcasts_db)}\n\n"
        f"⚙️ *פעולות מנהל:*\n"
        "השתמש בתפריט למטה או בפקודות:\n"
        "/stats - סטטיסטיקות מפורטות\n"
        "/broadcast - שידור לכולם\n"
        "/users - ניהול משתמשים\n"
        "/export - ייצוא נתונים\n"
        "/restart - אתחול בוט"
    )
    
    update.message.reply_text(
        admin_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )

def admin_stats(update, context):
    """Handle /stats command - Detailed stats for admin"""
    user = update.effective_user
    
    if not is_admin(user.id):
        update.message.reply_text("❌ *גישה נדחית!*", parse_mode=ParseMode.MARKDOWN)
        return
    
    log_message(update, 'stats')
    
    # Calculate uptime
    start_time = datetime.fromisoformat(bot_stats['start_time'])
    uptime = datetime.now() - start_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Get active users (last 7 days)
    week_ago = datetime.now() - timedelta(days=7)
    active_users = []
    active_groups = []
    
    for user_record in users_db:
        last_seen = datetime.fromisoformat(user_record.get('last_seen', start_time.isoformat()))
        if last_seen > week_ago:
            active_users.append(user_record)
    
    for group in groups_db:
        last_activity = datetime.fromisoformat(group.get('last_activity', start_time.isoformat()))
        if last_activity > week_ago:
            active_groups.append(group)
    
    # Calculate message distribution
    private_msgs = len([m for m in messages_db if m.get('chat_type') == 'private'])
    group_msgs = len([m for m in messages_db if m.get('chat_type') in ['group', 'supergroup']])
    
    stats_text = (
        f"📈 *סטטיסטיקות מפורטות - {BOT_NAME}*\n\n"
        f"*מידע כללי:*\n"
        f"• 🤖 *שם הבוט:* {BOT_NAME}\n"
        f"• 🆔 *ID הבוט:* `{BOT_ID}`\n"
        f"• 📅 *התחלה:* {start_time.strftime('%d/%m/%Y %H:%M:%S')}\n"
        f"• ⏱️ *זמן פעילות:* {days} ימים, {hours} שעות, {minutes} דקות\n"
        f"• 📝 *עדכון אחרון:* {bot_stats['last_update'] or 'אין'}\n\n"
        f"*פעילות:*\n"
        f"• 📨 *הודעות שקיבל:* {bot_stats['message_count']}\n"
        f"• 📨 *הודעות פרטיות:* {private_msgs}\n"
        f"• 📨 *הודעות קבוצות:* {group_msgs}\n"
        f"• 🚀 *פקודות /start:* {bot_stats['start_count']}\n"
        f"• 👥 *משתמשים ייחודיים:* {len(bot_stats['users'])}\n"
        f"• 👥 *משתמשים פעילים (7 ימים):* {len(active_users)}\n"
        f"• 👥 *קבוצות פעילות (7 ימים):* {len(active_groups)}\n"
        f"• 💾 *הודעות שמורות:* {len(messages_db)}\n\n"
        f"*שידורים אחרונים:*\n"
    )
    
    # Add broadcast history
    if broadcasts_db:
        for i, broadcast in enumerate(broadcasts_db[-5:], 1):
            timestamp = datetime.fromisoformat(broadcast['timestamp']).strftime('%d/%m %H:%M')
            sent = broadcast.get('sent_to', 0)
            failed = broadcast.get('failed', 0)
            stats_text += f"{i}. {broadcast['text'][:30]}... ({timestamp}) ✅{sent} ❌{failed}\n"
    else:
        stats_text += "אין שידורים עדיין\n"
    
    stats_text += f"\n*Webhook:* {WEBHOOK_URL or 'לא מוגדר'}"
    stats_text += f"\n*בוט ID:* `{BOT_ID}`"
    
    update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)

def broadcast_command(update, context):
    """Handle /broadcast command - Send message to all users"""
    user = update.effective_user
    
    if not is_admin(user.id):
        update.message.reply_text("❌ *גישה נדחית!* רק מנהל יכול להשתמש בפקודה זו.", parse_mode=ParseMode.MARKDOWN)
        return
    
    # Get broadcast message from command arguments
    if not context.args:
        update.message.reply_text(
            "❌ *שימוש:* /broadcast <הודעה>\n\n"
            "*דוגמה:*\n"
            "/broadcast שלום לכולם! זו הודעה חשובה.\n\n"
            "⚠️ *הערה:* ההודעה תישלח לכל המשתמשים והקבוצות.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    message = ' '.join(context.args)
    log_message(update, 'broadcast')
    
    # Send confirmation to admin
    update.message.reply_text(
        f"📢 *מתחיל שידור לכולם...*\n\n"
        f"*הודעה:* {message}\n"
        f"*מספר נמענים:* {len(users_db)} משתמשים, {len(groups_db)} קבוצות\n"
        f"⏳ שולח...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Record broadcast
    broadcast_record = {
        'id': len(broadcasts_db) + 1,
        'admin_id': user.id,
        'admin_name': user.first_name,
        'text': message,
        'timestamp': datetime.now().isoformat(),
        'sent_to_users': 0,
        'sent_to_groups': 0,
        'failed': 0
    }
    
    # Send to all users
    sent_users = 0
    sent_groups = 0
    failed = 0
    
    # Send to users
    for user_record in users_db:
        try:
            # Don't send to self
            if user_record['user_id'] == user.id:
                continue
                
            bot.send_message(
                chat_id=user_record['user_id'],
                text=f"📢 *הודעה מהמנהל:*\n\n{message}\n\n🤖 *נשלח ע\"י {BOT_NAME}*",
                parse_mode=ParseMode.MARKDOWN
            )
            sent_users += 1
            
            # Small delay to avoid rate limits
            time.sleep(0.05)
            
        except Exception as e:
            logger.error(f"Failed to send broadcast to user {user_record['user_id']}: {e}")
            failed += 1
    
    # Send to groups
    for group in groups_db:
        try:
            bot.send_message(
                chat_id=group['chat_id'],
                text=f"📢 *הודעה מהמנהל לכולם:*\n\n{message}\n\n🤖 *נשלח ע\"י {BOT_NAME}*",
                parse_mode=ParseMode.MARKDOWN
            )
            sent_groups += 1
            
            # Small delay to avoid rate limits
            time.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Failed to send broadcast to group {group['chat_id']}: {e}")
            failed += 1
    
    # Update broadcast record
    broadcast_record['sent_to_users'] = sent_users
    broadcast_record['sent_to_groups'] = sent_groups
    broadcast_record['failed'] = failed
    broadcasts_db.append(broadcast_record)
    save_json(BROADCASTS_FILE, broadcasts_db)
    
    # Send final report
    update.message.reply_text(
        f"✅ *שידור הושלם!*\n\n"
        f"📊 *תוצאות:*\n"
        f"• ✅ נשלח למשתמשים: {sent_users}\n"
        f"• ✅ נשלח לקבוצות: {sent_groups}\n"
        f"• ❌ נכשל: {failed}\n"
        f"• 👥 סה״כ נמענים: {len(users_db) + len(groups_db)}\n"
        f"• 🤖 *שולח:* {BOT_NAME} (ID: `{BOT_ID}`)\n"
        f"• 📝 *הודעה:* {message[:50]}...",
        parse_mode=ParseMode.MARKDOWN
    )

def users_command(update, context):
    """Handle /users command - User management for admin"""
    user = update.effective_user
    
    if not is_admin(user.id):
        update.message.reply_text("❌ *גישה נדחית!*", parse_mode=ParseMode.MARKDOWN)
        return
    
    log_message(update, 'users')
    
    # Sort users by last seen
    sorted_users = sorted(users_db, key=lambda x: x.get('last_seen', ''), reverse=True)
    
    users_text = (
        f"👥 *ניהול משתמשים - {BOT_NAME}*\n\n"
        f"📊 *סיכום:*\n"
        f"• משתמשים רשומים: {len(users_db)}\n"
        f"• מנהלים: {len([u for u in users_db if u.get('is_admin')])}\n"
        f"• משתמשים פרטיים: {len([u for u in users_db if u.get('chat_type') == 'private'])}\n"
        f"• משתמשי קבוצות: {len([u for u in users_db if u.get('chat_type') != 'private'])}\n\n"
        f"📅 *משתמשים אחרונים (10):*\n"
    )
    
    for i, user_record in enumerate(sorted_users[:10], 1):
        last_seen = datetime.fromisoformat(user_record.get('last_seen', bot_stats['start_time']))
        days_ago = (datetime.now() - last_seen).days
        status = "🟢" if days_ago < 1 else "🟡" if days_ago < 7 else "🔴"
        
        users_text += (
            f"{i}. {user_record.get('first_name', 'ללא שם')} "
            f"(@{user_record.get('username', 'ללא')}) "
            f"- {user_record.get('message_count', 0)} הודעות "
            f"{status} {days_ago} יום\n"
        )
    
    users_text += (
        f"\n⚙️ *פקודות נוספות:*\n"
        f"/userinfo <id> - פרטי משתמש\n"
        f"/export users - ייצוא משתמשים\n"
        f"\n🤖 *ID הבוט:* `{BOT_ID}`"
    )
    
    update.message.reply_text(users_text, parse_mode=ParseMode.MARKDOWN)

def export_command(update, context):
    """Handle /export command - Export data"""
    user = update.effective_user
    
    if not is_admin(user.id):
        update.message.reply_text("❌ *גישה נדחית!*", parse_mode=ParseMode.MARKDOWN)
        return
    
    log_message(update, 'export')
    
    export_text = (
        f"📤 *ייצוא נתונים - {BOT_NAME}*\n\n"
        f"*נתונים זמינים לייצוא:*\n"
        f"• משתמשים: {len(users_db)} רשומות\n"
        f"• קבוצות: {len(groups_db)} רשומות\n"
        f"• הודעות: {len(messages_db)} רשומות\n"
        f"• שידורים: {len(broadcasts_db)} רשומות\n\n"
        f"⚙️ *אופציות ייצוא:*\n"
        f"/export users - ייצוא משתמשים\n"
        f"/export groups - ייצוא קבוצות\n"
        f"/export messages - ייצוא הודעות\n"
        f"/export all - ייצוא הכול\n\n"
        f"💾 *הנתונים נשמרים אוטומטית ב:*\n"
        f"`{USERS_FILE}`\n`{GROUPS_FILE}`\n`{MESSAGES_FILE}`"
    )
    
    update.message.reply_text(export_text, parse_mode=ParseMode.MARKDOWN)

def restart_command(update, context):
    """Handle /restart command - Restart bot"""
    user = update.effective_user
    
    if not is_admin(user.id):
        update.message.reply_text("❌ *גישה נדחית!*", parse_mode=ParseMode.MARKDOWN)
        return
    
    log_message(update, 'restart')
    
    restart_text = (
        f"♻️ *אתחול בוט - {BOT_NAME}*\n\n"
        f"*הפעולה תבצע:*\n"
        f"1. שמירת כל הנתונים הנוכחיים\n"
        f"2. איפוס סטטיסטיקות בזיכרון\n"
        f"3. אתחול תהליך הבוט\n\n"
        f"📊 *נתונים לפני אתחול:*\n"
        f"• הודעות: {bot_stats['message_count']}\n"
        f"• משתמשים: {len(bot_stats['users'])}\n"
        f"• קבוצות: {len(bot_stats['groups'])}\n\n"
        f"⚠️ *שים לב:*\n"
        f"בסביבת Railway, האתחול יתבצע אוטומטית\n"
        f"לאחר פריסה חדשה או שינוי בקוד.\n\n"
        f"🤖 *ID הבוט:* `{BOT_ID}`"
    )
    
    update.message.reply_text(restart_text, parse_mode=ParseMode.MARKDOWN)
    
    # Note: In Railway, restart happens automatically on redeploy
    # For actual restart, you'd need to implement a proper restart mechanism

def handle_text(update, context):
    """Handle regular text messages (with buttons and group mentions)"""
    message = update.message
    if not message or not message.text:
        return
    
    # Check if we should respond
    if not should_respond(update):
        return
    
    log_message(update, 'text')
    user = update.effective_user
    chat = update.effective_chat
    
    text = message.text.lower()
    
    # Handle button presses
    if text == "📊 סטטיסטיקות":
        bot_info(update, context)
    
    elif text == "ℹ️ מידע על הבוט":
        about_command(update, context)
    
    elif text == "🆔 הצג id שלי":
        show_id(update, context)
    
    elif text == "🔧 תפריט מנהל" and is_admin(user.id):
        admin_panel(update, context)
    
    elif text == "👤 אודותיי":
        user_info = f"👤 *אודותיך:*\nשם: {user.first_name}\nID: `{user.id}`\n"
        if user.username:
            user_info += f"Username: @{user.username}\n"
        user_info += f"\n🤖 *הבוט:* {BOT_NAME}\nID הבוט: `{BOT_ID}`"
        update.message.reply_text(user_info, parse_mode=ParseMode.MARKDOWN)
    
    elif text == "❓ עזרה":
        help_command(update, context)
    
    elif text == "🔄 רענן":
        update.message.reply_text("🔄 *תפריט רענן!*", parse_mode=ParseMode.MARKDOWN)
        menu_command(update, context)
    
    elif text == "📢 שידור לכולם" and is_admin(user.id):
        update.message.reply_text(
            "📢 *לשידור לכולם:*\nהשתמש בפקודה /broadcast <הודעה>",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif text == "📈 סטטיסטיקות מפורטות" and is_admin(user.id):
        admin_stats(update, context)
    
    elif text == "🏠 לתפריט הראשי":
        menu_command(update, context)
    
    elif text == "⚙️ הגדרות" and is_admin(user.id):
        settings_text = (
            f"⚙️ *הגדרות הבוט - {BOT_NAME}*\n\n"
            f"🔧 *פעולות זמינות:*\n"
            f"• שינוי שם הבוט (מתבצע ב @BotFather)\n"
            f"• שינוי תמונה (מתבצע ב @BotFather)\n"
            f"• הגדרת Webhook: {'מוגדר ✅' if WEBHOOK_URL else 'לא מוגדר'}\n"
            f"• ID מנהל: {ADMIN_USER_ID}\n"
            f"• ID הבוט: `{BOT_ID}`\n\n"
            f"📊 *מאגר נתונים:*\n"
            f"• משתמשים: {len(users_db)}\n"
            f"• קבוצות: {len(groups_db)}\n"
            f"• הודעות: {len(messages_db)}\n"
            f"• שידורים: {len(broadcasts_db)}\n\n"
            f"💡 *עדכון הגדרות:*\n"
            f"הגדרות סביבה מתבצעות ב-Railway"
        )
        update.message.reply_text(settings_text, parse_mode=ParseMode.MARKDOWN)
    
    elif text == "🔄 אתחול בוט" and is_admin(user.id):
        restart_command(update, context)
    
    # Handle group mentions
    elif BOT_USERNAME and f"@{BOT_USERNAME}" in message.text:
        mentioned_text = message.text.lower()
        
        if "סטטוס" in mentioned_text or "status" in mentioned_text:
            update.message.reply_text(
                f"🤖 *סטטוס {BOT_NAME}:*\n"
                f"✅ פעיל וזמין\n"
                f"📊 {bot_stats['message_count']} הודעות\n"
                f"👥 {len(bot_stats['users'])} משתמשים\n"
                f"🆔 ID: `{BOT_ID}`",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif "מידע" in mentioned_text or "info" in mentioned_text:
            about_command(update, context)
        
        elif "עזרה" in mentioned_text or "help" in mentioned_text:
            help_command(update, context)
        
        elif "id" in mentioned_text or "מספר" in mentioned_text:
            show_id(update, context)
        
        elif "בוט" in mentioned_text or "רובוט" in mentioned_text:
            update.message.reply_text(
                f"🤖 *כן, אני {BOT_NAME}!*\n"
                f"השתמש ב @{BOT_USERNAME} עזרה כדי לראות את הפקודות.",
                parse_mode=ParseMode.MARKDOWN
            )
        
        else:
            update.message.reply_text(
                f"🤖 *היי, אני {BOT_NAME}!*\n"
                f"נכתב: {message.text}\n\n"
                f"📌 *ניתן לבקש ממני:*\n"
                f"`@{BOT_USERNAME} סטטוס` - מצב הבוט\n"
                f"`@{BOT_USERNAME} עזרה` - רשימת פקודות\n"
                f"`@{BOT_USERNAME} מידע` - אודות הבוט\n"
                f"\n🆔 *ID הבוט שלי:* `{BOT_ID}`",
                parse_mode=ParseMode.MARKDOWN
            )
    
    # Default echo for private chats
    elif chat.type == 'private':
        response = f"📝 *אתה כתבת:*\n`{message.text}`\n\n🤖 *ID הבוט:* `{BOT_ID}`"
        update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

def unknown(update, context):
    """Handle unknown commands"""
    log_message(update, 'unknown')
    
    # Check if it's a command for our bot in group
    message = update.message
    if message and message.text and message.entities:
        for entity in message.entities:
            if entity.type == 'bot_command' and BOT_USERNAME and f"@{BOT_USERNAME}" in message.text:
                update.message.reply_text(
                    f"❓ *פקודה לא מזוהה ל{BOT_NAME}*\n"
                    f"השתמש ב @{BOT_USERNAME} עזרה כדי לראות את הפקודות.\n\n"
                    f"🆔 *ID הבוט:* `{BOT_ID}`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
    
    update.message.reply_text(
        "❓ *פקודה לא מזוהה*\n"
        "השתמש ב /help כדי לראות את רשימת הפקודות.",
        parse_mode=ParseMode.MARKDOWN
    )

def error_handler(update, context):
    """Handle errors in the bot"""
    error_msg = str(context.error) if context.error else "Unknown error"
    logger.error(f"Update {update} caused error: {error_msg}", exc_info=True)
    
    try:
        if update and update.effective_chat:
            # Only send error details to admin
            user = update.effective_user
            if user and is_admin(user.id):
                update.effective_chat.send_message(
                    f"❌ *שגיאה בבוט:*\n\n"
                    f"```\n{error_msg[:200]}\n```\n\n"
                    f"🤖 *ID הבוט:* `{BOT_ID}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                # For regular users - general message
                update.effective_chat.send_message(
                    f"⚠️ *אירעה שגיאה* אנא נסה שוב מאוחר יותר.\n\n"
                    f"🤖 *ID הבוט:* `{BOT_ID}`",
                    parse_mode=ParseMode.MARKDOWN
                )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

# ==================== SETUP HANDLERS ====================
# Command handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("help", help_command))
dispatcher.add_handler(CommandHandler("about", about_command))
dispatcher.add_handler(CommandHandler("botinfo", botinfo_command))
dispatcher.add_handler(CommandHandler("menu", menu_command))
dispatcher.add_handler(CommandHandler("id", show_id))
dispatcher.add_handler(CommandHandler("info", bot_info))
dispatcher.add_handler(CommandHandler("ping", ping))
dispatcher.add_handler(CommandHandler("admin", admin_panel))
dispatcher.add_handler(CommandHandler("stats", admin_stats))
dispatcher.add_handler(CommandHandler("broadcast", broadcast_command, pass_args=True))
dispatcher.add_handler(CommandHandler("users", users_command))
dispatcher.add_handler(CommandHandler("export", export_command))
dispatcher.add_handler(CommandHandler("restart", restart_command))

# Text message handler (for buttons and group mentions)
dispatcher.add_handler(MessageHandler(Filters.text, handle_text))

# Unknown command handler (must be last)
dispatcher.add_handler(MessageHandler(Filters.command, unknown))

# Add error handler
dispatcher.add_error_handler(error_handler)

# ==================== FLASK ROUTES ====================
@app.route('/')
def home():
    """Home page"""
    return jsonify({
        "status": "online",
        "service": "telegram-bot",
        "bot": {
            "name": BOT_NAME,
            "username": BOT_USERNAME,
            "id": BOT_ID,
            "link": f"t.me/{BOT_USERNAME}" if BOT_USERNAME else None
        },
        "stats": {
            "uptime": bot_stats['start_time'],
            "messages": bot_stats['message_count'],
            "unique_users": len(bot_stats['users']),
            "active_groups": len(bot_stats['groups']),
            "starts": bot_stats['start_count']
        },
        "storage": {
            "users": len(users_db),
            "messages": len(messages_db),
            "broadcasts": len(broadcasts_db),
            "groups": len(groups_db)
        },
        "features": {
            "keyboards": True,
            "group_mentions": True,
            "auto_discovery": True,
            "admin_tools": True,
            "broadcast": True
        }
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook endpoint"""
    # Check webhook secret if set
    if WEBHOOK_SECRET and WEBHOOK_SECRET.strip():
        secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token')
        if secret != WEBHOOK_SECRET:
            logger.warning(f"Unauthorized webhook attempt. Expected: '{WEBHOOK_SECRET}', Got: '{secret}'")
            return 'Unauthorized', 403
    else:
        logger.warning("WEBHOOK_SECRET not set, skipping authentication")
    
    try:
        data = request.get_json()
        
        # Log webhook request
        if 'message' in data and 'text' in data['message']:
            msg = data['message']
            logger.info(f"📨 Webhook: {msg['text'][:50]}...")
        
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
        "bot": {
            "name": BOT_NAME,
            "id": BOT_ID,
            "username": BOT_USERNAME,
            "running": True
        },
        "stats": {
            "messages": bot_stats['message_count'],
            "users": len(bot_stats['users']),
            "groups": len(bot_stats['groups']),
            "uptime": bot_stats['start_time']
        }
    })

@app.route('/bot/info')
def bot_info_endpoint():
    """Endpoint to get bot info"""
    return jsonify({
        "bot": {
            "id": BOT_ID,
            "username": BOT_USERNAME,
            "name": BOT_NAME,
            "first_name": BOT_NAME,
            "is_bot": True,
            "link": f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else None,
            "webhook": bool(WEBHOOK_URL)
        },
        "server": {
            "url": WEBHOOK_URL,
            "platform": "Railway",
            "status": "running"
        }
    })

@app.route('/admin/dashboard')
def admin_dashboard():
    """Admin dashboard (requires secret)"""
    auth = request.args.get('auth')
    if auth != WEBHOOK_SECRET:
        return jsonify({"error": "Unauthorized"}), 403
    
    return jsonify({
        "bot_info": {
            "id": BOT_ID,
            "name": BOT_NAME,
            "username": BOT_USERNAME,
            "admin_id": ADMIN_USER_ID
        },
        "stats": bot_stats,
        "storage": {
            "users": len(users_db),
            "messages": len(messages_db),
            "broadcasts": len(broadcasts_db),
            "groups": len(groups_db)
        },
        "endpoints": {
            "health": "/health",
            "bot_info": "/bot/info",
            "webhook": "/webhook",
            "home": "/"
        }
    })

# ==================== INITIALIZATION ====================
def setup_webhook():
    """Setup webhook if URL is provided"""
    if WEBHOOK_URL:
        try:
            # Ensure webhook URL ends with /webhook
            webhook_url = WEBHOOK_URL.rstrip('/') + '/webhook'
            bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Webhook configured: {webhook_url}")
            logger.info(f"🤖 Bot ID: {BOT_ID}, Username: @{BOT_USERNAME}")
        except Exception as e:
            logger.warning(f"⚠️ Webhook setup failed: {e}")

if __name__ == '__main__':
    logger.info("🚀 Starting Advanced Telegram Bot")
    
    # Setup webhook
    setup_webhook()
    
    # Log startup info
    logger.info(f"🤖 Bot: {BOT_NAME} (@{BOT_USERNAME}, ID: {BOT_ID})")
    logger.info(f"👑 Admin ID: {ADMIN_USER_ID or 'Not configured'}")
    logger.info(f"💾 Storage: {len(users_db)} users, {len(groups_db)} groups, {len(messages_db)} messages")
    logger.info(f"🎯 Features: Keyboards, Group mentions, Auto-discovery, Broadcast")
    logger.info(f"🌐 Flask starting on port {PORT}")
    
    # Start Flask
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
