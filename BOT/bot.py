# /BOT/bot.py  (diagnostics)
import os
import socket
import ssl
import logging
from datetime import datetime, timezone
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# env (no hard failure)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
PORT = int(os.getenv("PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("diagnostics")

app = FastAPI(title="Deployment Diagnostics")

def now_ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "time": now_ts(), "service": "diagnostics"})

@app.get("/env")
async def env():
    return JSONResponse({
        "TELEGRAM_BOT_TOKEN_present": bool(TELEGRAM_BOT_TOKEN),
        "WEBHOOK_URL_present": bool(WEBHOOK_URL),
        "PORT": PORT,
        "time": now_ts()
    })

@app.get("/routes")
async def routes():
    return JSONResponse({"ok": True, "routes": [r.path for r in app.routes]})

@app.get("/net/check")
async def net_check():
    if not WEBHOOK_URL:
        return JSONResponse({"ok": False, "error": "WEBHOOK_URL not set"})
    try:
        host = WEBHOOK_URL.replace("https://", "").split("/")[0]
        socket.getaddrinfo(host, 443)
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=5) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        return JSONResponse({"ok": True, "host": host, "cert_subject": cert.get("subject")})
    except Exception as e:
        logger.exception("net_check failed")
        return JSONResponse({"ok": False, "error": str(e)})

def tg_api(method: str, params=None, files=None):
    if not TELEGRAM_BOT_TOKEN:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN not set"}
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        r = requests.post(url, params=params or {}, files=files, timeout=15)
        try:
            return r.json()
        except Exception:
            return {"ok": False, "http_status": r.status_code, "text": r.text}
    except Exception as e:
        logger.exception("tg_api request failed")
        return {"ok": False, "error": str(e)}

@app.get("/telegram/getWebhookInfo")
async def telegram_get_webhook_info():
    return JSONResponse(tg_api("getWebhookInfo"))

@app.post("/telegram/setWebhookManual")
async def telegram_set_webhook_manual(request: Request):
    if not WEBHOOK_URL or not TELEGRAM_BOT_TOKEN:
        return JSONResponse({"ok": False, "error": "WEBHOOK_URL or TELEGRAM_BOT_TOKEN missing"})
    webhook_endpoint = f"{WEBHOOK_URL.rstrip('/')}/{TELEGRAM_BOT_TOKEN}"
    return JSONResponse(tg_api("setWebhook", params={"url": webhook_endpoint}))

@app.post("/telegram/deleteWebhookManual")
async def telegram_delete_webhook_manual():
    return JSONResponse(tg_api("deleteWebhook", params={"drop_pending_updates": "true"}))

@app.get("/telegram/getMe")
async def telegram_get_me():
    return JSONResponse(tg_api("getMe"))

@app.get("/debug/full")
async def debug_full():
    out = {
        "time": now_ts(),
        "env": {"TELEGRAM_BOT_TOKEN_present": bool(TELEGRAM_BOT_TOKEN), "WEBHOOK_URL_present": bool(WEBHOOK_URL), "PORT": PORT},
        "routes": [r.path for r in app.routes],
        "net_check": None,
        "telegram_getMe": None,
        "telegram_getWebhookInfo": None
    }
    if WEBHOOK_URL:
        try:
            host = WEBHOOK_URL.replace("https://", "").split("/")[0]
            socket.getaddrinfo(host, 443)
            out["net_check"] = {"host": host, "resolved": True}
        except Exception as e:
            out["net_check"] = {"error": str(e)}
    out["telegram_getMe"] = tg_api("getMe")
    out["telegram_getWebhookInfo"] = tg_api("getWebhookInfo")
    return JSONResponse(out)
