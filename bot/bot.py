#!/usr/bin/env python3
# bot.py
# Flask WSGI app for Telegram webhook. Designed for Railway / similar hosts.
# Requirements: Flask, pyTelegramBotAPI, requests
# Recommended start command: gunicorn --bind 0.0.0.0:$PORT bot:app --workers 2

import os
import time
import threading
import logging
from flask import Flask, request, abort, jsonify
import telebot
import requests

# --- Configuration from environment ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://me-production-8bf5.up.railway.app
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change_this_secret")
AUTO_SET_WEBHOOK = os.getenv("AUTO_SET_WEBHOOK", "false").lower() in ("1", "true", "yes")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
TELEGRAM_API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

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
        if message.text:
            reply = f"קיבלתי: {message.text}"
        else:
            reply = "קיבלתי את ההודעה שלך — תודה!"
        bot.send_message(message.chat.id, reply)
        logger.info("Replied to chat_id=%s message_id=%s", getattr(message.chat, "id", None), getattr(message, "message_id", None))
    except Exception:
        logger.exception("Failed to reply to message")

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
    except Exception:
        logger.exception("Error processing update")
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
            r = requests.get(f"{TELEGRAM_API_BASE}/deleteWebhook", timeout=10)
            logger.debug("deleteWebhook response: %s", r.text)
        except Exception:
            logger.debug("deleteWebhook request failed (ignored)")
        r = requests.post(f"{TELEGRAM_API_BASE}/setWebhook", data={"url": webhook_url}, timeout=10)
        logger.info("set_webhook response: %s", r.text)
        return r.ok and r.json().get("ok", False)
    except Exception:
        logger.exception("Failed to set webhook")
        return False

def delete_webhook():
    try:
        r = requests.get(f"{TELEGRAM_API_BASE}/deleteWebhook", timeout=10)
        logger.info("delete_webhook response: %s", r.text)
        return r.ok and r.json().get("ok", False)
    except Exception:
        logger.exception("Failed to delete webhook")
        return False

def get_webhook_info():
    try:
        r = requests.get(f"{TELEGRAM_API_BASE}/getWebhookInfo", timeout=10)
        logger.debug("getWebhookInfo response: %s", r.text)
        return r.json() if r.ok else None
    except Exception:
        logger.exception("Failed to get webhook info")
        return None

def maybe_auto_set_webhook_background():
    """If AUTO_SET_WEBHOOK is enabled, set webhook in a background thread."""
    if AUTO_SET_WEBHOOK and WEBHOOK_URL:
        def worker():
            time.sleep(1)
            success = set_webhook()
            if not success:
                logger.warning("Auto set_webhook failed; you may need to run setWebhook manually")
        t = threading.Thread(target=worker, daemon=True)
        t.start()

# Optional admin endpoints (protected by WEBHOOK_SECRET)
@app.route("/admin/set_webhook/<secret>", methods=["POST"])
def admin_set_webhook(secret):
    if secret != WEBHOOK_SECRET:
        abort(403)
    ok = set_webhook()
    return jsonify(result=ok), (200 if ok else 500)

@app.route("/admin/delete_webhook/<secret>", methods=["POST"])
def admin_delete_webhook(secret):
    if secret != WEBHOOK_SECRET:
        abort(403)
    ok = delete_webhook()
    return jsonify(result=ok), (200 if ok else 500)

@app.route("/admin/get_webhook_info/<secret>", methods=["GET"])
def admin_get_webhook_info(secret):
    if secret != WEBHOOK_SECRET:
        abort(403)
    info = get_webhook_info()
    return jsonify(result=info), (200 if info is not None else 500)

# --- Startup behavior ---
maybe_auto_set_webhook_background()

# --- Local run support ---
if __name__ == "__main__":
    maybe_auto_set_webhook_background()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
