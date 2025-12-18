#!/usr/bin/env python3
# bot.py
# Flask WSGI app for Telegram webhook. Designed for Railway / similar hosts.
# Requirements: Flask, pyTelegramBotAPI
# Recommended start command: gunicorn --bind 0.0.0.0:$PORT bot:app --workers 2

import os
import time
import threading
import logging
from flask import Flask, request, abort, jsonify
import telebot

# --- Configuration from environment ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://me-production-8bf5.up.railway.app
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change_this_secret")
AUTO_SET_WEBHOOK = os.getenv("AUTO_SET_WEBHOOK", "false").lower() in ("1", "true", "yes")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is required")

# --- Logging ---
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("telegram-bot")

# --- Flask and Telebot setup ---
app = Flask(__name__)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, threaded=True)

# --- Handlers ---
@bot.message_handler(func=lambda m: True)
def handle_all_messages(message):
    try:
        # Simple echo behavior; replace with your logic
        if message.text:
            reply = f"קיבלתי: {message.text}"
        else:
            reply = "קיבלתי את ההודעה שלך — תודה!"
        bot.send_message(message.chat.id, reply)
        logger.info("Replied to chat_id=%s message_id=%s", message.chat.id, getattr(message, "message_id", None))
    except Exception as e:
        logger.exception("Failed to reply to message: %s", e)

# --- Webhook endpoint ---
@app.route("/webhook/<secret>", methods=["POST"])
def webhook(secret):
    if secret != WEBHOOK_SECRET:
        logger.warning("Forbidden webhook access with secret=%s", secret)
        abort(403)
    # Accept JSON only
    if not request.is_json:
        logger.warning("Rejected non-JSON webhook request")
        abort(400)
    try:
        raw = request.get_data(as_text=True)
        logger.debug("RAW UPDATE: %s", raw)
        update = request.get_json(force=True)
        bot.process_new_updates([telebot.types.Update.de_json(update)])
    except Exception as e:
        logger.exception("Error processing update: %s", e)
        # Return 200 to avoid Telegram retry storms for transient errors,
        # but log the exception for investigation.
        return "OK", 200
    return "OK", 200

# --- Health endpoints (Railway default is /health) ---
@app.route("/health", methods=["GET"])
def health():
    return "ok", 200

@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify(status="ok"), 200

# --- Webhook management helpers ---
def set_webhook():
    """Set webhook to WEBHOOK_URL/webhook/WEBHOOK_SECRET. Safe to call repeatedly."""
    if not WEBHOOK_URL:
        logger.warning("WEBHOOK_URL not set; skipping set_webhook()")
        return False
    webhook_url = f"{WEBHOOK_URL.rstrip('/')}/webhook/{WEBHOOK_SECRET}"
    try:
        # Remove existing webhook first (best-effort)
        try:
            bot.remove_webhook()
        except Exception:
            # ignore remove errors
            pass
        result = bot.set_webhook(url=webhook_url)
        logger.info("set_webhook result=%s url=%s", result, webhook_url)
        return True
    except Exception as e:
        logger.exception("Failed to set webhook: %s", e)
        return False

def maybe_auto_set_webhook_background():
    """If AUTO_SET_WEBHOOK is enabled, set webhook in a background thread."""
    if AUTO_SET_WEBHOOK and WEBHOOK_URL:
        def worker():
            # small delay to allow the process to be fully ready
            time.sleep(1)
            success = set_webhook()
            if not success:
                logger.warning("Auto set_webhook failed; you may need to run setWebhook manually")
        t = threading.Thread(target=worker, daemon=True)
        t.start()

# Optional admin endpoint to trigger set_webhook (protected by WEBHOOK_SECRET)
@app.route("/admin/set_webhook/<secret>", methods=["POST"])
def admin_set_webhook(secret):
    if secret != WEBHOOK_SECRET:
        abort(403)
    ok = set_webhook()
    return jsonify(result=ok), (200 if ok else 500)

# --- Startup behavior ---
# When imported by gunicorn, this module-level code runs once.
maybe_auto_set_webhook_background()

# --- Local run support ---
if __name__ == "__main__":
    # For local testing only. In production use gunicorn as recommended.
    maybe_auto_set_webhook_background()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
