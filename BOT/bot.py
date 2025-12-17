# bot.py
import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import yfinance as yf
import ccxt
from dotenv import load_dotenv

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ---------- Env ----------
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://web-production-112f6.up.railway.app
DEFAULT_EXCHANGE = os.getenv("DEFAULT_EXCHANGE", "binance")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID")  # optional numeric Telegram id

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing in environment")
if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL is missing in environment")

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("telegram-webhook-bot")

# ---------- FastAPI app ----------
app = FastAPI(title="Telegram Webhook Trade Bot")
application: Application | None = None
_ready = False  # readiness flag: becomes True after successful set_webhook

# ---------- Utilities ----------
def fmt_ts(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def safe_float(x):
    try:
        return float(x)
    except Exception:
        return None

def normalize_symbol_for_exchange(symbol: str) -> str:
    s = symbol.upper().replace("-", "").replace("_", "")
    if "/" in symbol:
        return symbol.upper()
    if s.endswith("USDT"):
        return s[:-4] + "/USDT"
    if s.endswith("USD"):
        return s[:-3] + "/USD"
    return symbol.upper()

YF_SYMBOL_MAP = {
    "DXY": "DX-Y.NYB",
    "CL": "CL=F",
    "WTI": "CL=F",
    "BRENT": "BZ=F",
    "GOLD": "GC=F",
    "SPX": "^GSPC",
    "NDX": "^NDX",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
}
def resolve_symbol(symbol: str) -> str:
    s = symbol.upper()
    return YF_SYMBOL_MAP.get(s, symbol)

# ---------- CCXT helpers ----------
def get_exchange(name: str = DEFAULT_EXCHANGE):
    try:
        ex_class = getattr(ccxt, name)
        ex = ex_class({"enableRateLimit": True, "timeout": 10000})
        return ex
    except Exception as e:
        logger.exception("Exchange init failed")
        raise RuntimeError(f"Exchange '{name}' not available: {e}") from e

async def ccxt_ticker(symbol: str, exchange_name: str = DEFAULT_EXCHANGE):
    loop = asyncio.get_event_loop()
    ex = get_exchange(exchange_name)
    def _fetch():
        return ex.fetch_ticker(symbol)
    return await loop.run_in_executor(None, _fetch)

async def ccxt_ohlcv(symbol: str, timeframe: str = "1m", limit: int = 200, exchange_name: str = DEFAULT_EXCHANGE):
    loop = asyncio.get_event_loop()
    ex = get_exchange(exchange_name)
    def _fetch():
        return ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    data = await loop.run_in_executor(None, _fetch)
    df = pd.DataFrame(data, columns=["ts","open","high","low","close","volume"])
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df

# ---------- Indicators ----------
def sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n).mean()

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(alpha=1/period, adjust=False).mean()
    ma_down = down.ewm(alpha=1/period, adjust=False).mean()
    rs = ma_up / (ma_down + 1e-12)
    return 100 - (100 / (1 + rs))

# ---------- Correlation ----------
def compute_correlation(symbols: list[str], lookback_days: int = 30, interval: str = "60m"):
    data = {}
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    for s in symbols:
        yf_symbol = resolve_symbol(s)
        try:
            df = yf.download(yf_symbol, start=start, end=end, interval=interval, progress=False, auto_adjust=True)
            if df is None or df.empty:
                continue
            data[s] = df["Close"].rename(s)
        except Exception as e:
            logger.warning(f"Failed to load {s}: {e}")
    if not data:
        return None, None
    aligned = pd.concat(data.values(), axis=1).dropna()
    returns = aligned.pct_change().dropna()
    corr = returns.corr()
    return corr, aligned.index[-1] if not aligned.empty else None

# ---------- Admin helper ----------
def is_admin(update: Update) -> bool:
    try:
        if ADMIN_USER_ID:
            return str(update.effective_user.id) == str(ADMIN_USER_ID)
    except Exception:
        pass
    return False

# ---------- Telegram command handlers ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ברוך הבא לבוט נתוני שוק (webhook).\n\n"
        "פקודות:\n"
        "/price <symbol> — מחיר אחרון (למשל BTCUSDT)\n"
        "/ohlcv <symbol> <timeframe> — נר אחרון (ברירת מחדל 1m)\n"
        "/indicators <symbol> — SMA/RSI בסיסי\n"
        "/correlate <symbols...> — קורולציות (למשל BTCUSD DXY CL=F)\n"
        "/help — עזרה\n\n"
        "המידע לצורכי אינפורמציה בלבד, לא ייעוץ או המלצה."
    )
    await update.message.reply_text(text)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_cmd(update, context)

async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("שימוש: /price <symbol>\nדוגמה: /price BTCUSDT")
        return
    raw = context.args[0]
    symbol = normalize_symbol_for_exchange(raw)
    try:
        t = await ccxt_ticker(symbol)
        price = safe_float(t.get("last"))
        bid = safe_float(t.get("bid"))
        ask = safe_float(t.get("ask"))
        ts = t.get("datetime") or fmt_ts(datetime.now(timezone.utc))
        text = (
            f"סימול: {symbol}\n"
            f"מחיר אחרון: {price}\n"
            f"Bid: {bid} | Ask: {ask}\n"
            f"זמן: {ts}\n"
            f"בורסה: {DEFAULT_EXCHANGE}"
        )
        await update.message.reply_text(text)
    except Exception as e:
        logger.exception("price_cmd error")
        await update.message.reply_text(f"נכשל בקבלת מחיר ל-{symbol}: {e}")

async def ohlcv_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("שימוש: /ohlcv <symbol> <timeframe>\nדוגמה: /ohlcv BTCUSDT 5m")
        return
    raw = context.args[0]
    timeframe = context.args[1] if len(context.args) > 1 else "1m"
    symbol = normalize_symbol_for_exchange(raw)
    try:
        df = await ccxt_ohlcv(symbol, timeframe=timeframe, limit=50)
        last = df.iloc[-1]
        text = (
            f"OHLCV ({symbol}, {timeframe}) - נר אחרון:\n"
            f"פתיחה: {last['open']}\n"
            f"גבוה: {last['high']}\n"
            f"נמוך: {last['low']}\n"
            f"סגירה: {last['close']}\n"
            f"מחזור: {last['volume']}\n"
            f"זמן: {fmt_ts(last['dt'])}"
        )
        await update.message.reply_text(text)
    except Exception as e:
        logger.exception("ohlcv_cmd error")
        await update.message.reply_text(f"שגיאה בקבלת OHLCV ל-{symbol}: {e}")

async def indicators_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("שימוש: /indicators <symbol>\nדוגמה: /indicators BTCUSDT")
        return
    raw = context.args[0]
    symbol = normalize_symbol_for_exchange(raw)
    try:
        df = await ccxt_ohlcv(symbol, timeframe="1m", limit=200)
        closes = df["close"]
        sma20 = sma(closes, 20).iloc[-1]
        sma50 = sma(closes, 50).iloc[-1]
        rsi14 = rsi(closes, 14).iloc[-1]
        last_close = closes.iloc[-1]
        ts = df["dt"].iloc[-1]
        sigs = []
        if last_close > sma20 and last_close > sma50:
            sigs.append("מחיר מעל SMA20/50")
        if rsi14 > 70:
            sigs.append("RSI גבוה (מעל 70)")
        elif rsi14 < 30:
            sigs.append("RSI נמוך (מתחת 30)")
        if not sigs:
            sigs.append("אין אות ברור לפי אינדיקטורים בסיסיים")
        text = (
            f"({symbol}) אינדיקטורים בסיסיים להמחשה בלבד:\n"
            f"מחיר: {last_close:.4f}\n"
            f"SMA20: {sma20:.4f} | SMA50: {sma50:.4f}\n"
            f"RSI14: {rsi14:.2f}\n"
            f"סיכום: {', '.join(sigs)}\n"
            f"זמן: {fmt_ts(ts)}\n"
            f"המידע אינו ייעוץ או המלצה."
        )
        await update.message.reply_text(text)
    except Exception as e:
        logger.exception("indicators_cmd error")
        await update.message.reply_text(f"שגיאה בחישוב אינדיקטורים ל-{symbol}: {e}")

async def correlate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("שימוש: /correlate <symbol1> <symbol2> [symbol3 ...]\nדוגמה: /correlate BTCUSD DXY CL=F")
        return
    symbols = context.args
    try:
        corr, ts = compute_correlation(symbols, lookback_days=30, interval="60m")
        if corr is None:
            await update.message.reply_text("לא הצלחתי לטעון נתונים לקורולציה. נסה סימולים אחרים.")
            return
        lines = []
        header = "קורולציות (תשואות, חלון ~30 ימים, אינטרוול 60m):"
        lines.append(header)
        for i in corr.index:
            row_vals = [f"{corr.loc[i,j]:.2f}" for j in corr.columns]
            lines.append(f"{i}: " + " | ".join(row_vals))
        footer = f"עדכון אחרון: {fmt_ts(ts)}" if ts else ""
        await update.message.reply_text("\n".join(lines + [footer]))
    except Exception as e:
        logger.exception("correlate_cmd error")
        await update.message.reply_text(f"שגיאה בחישוב קורולציה: {e}")

# ---------- Build Application ----------
def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("ohlcv", ohlcv_cmd))
    app.add_handler(CommandHandler("indicators", indicators_cmd))
    app.add_handler(CommandHandler("correlate", correlate_cmd))
    return app

# ---------- FastAPI lifecycle: webhook mode with retries and debug ----------
@app.on_event("startup")
async def on_startup():
    global application, _ready
    logger.info("Startup: building Telegram Application (webhook mode)...")
    application = build_application()
    webhook_endpoint = f"{WEBHOOK_URL.rstrip('/')}/{TELEGRAM_BOT_TOKEN}"

    # try to delete existing webhook (non-fatal)
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Deleted existing webhook (if any)")
    except Exception as e:
        logger.debug("delete_webhook non-fatal: %s", e)

    # attempt to set webhook with retries and logging of responses
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            resp = await application.bot.set_webhook(url=webhook_endpoint)
            logger.info("set_webhook response: %s", resp)
            # verify via getWebhookInfo
            try:
                info = await application.bot.get_webhook_info()
                # info may be a telegram.WebhookInfo object; convert to dict if possible
                try:
                    info_dict = info.to_dict()
                except Exception:
                    info_dict = str(info)
                logger.info("getWebhookInfo after set: %s", info_dict)
            except Exception as e:
                logger.warning("get_webhook_info check failed: %s", e)
            _ready = True
            break
        except Exception as e:
            logger.warning("Attempt %d to set webhook failed: %s", attempt, e)
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.exception("Failed to set webhook after retries")

@app.on_event("shutdown")
async def on_shutdown():
    global application
    logger.info("Shutting down webhook bot...")
    try:
        if application:
            await application.bot.delete_webhook()
            await application.stop()
    except Exception as e:
        logger.warning("Shutdown issue: %s", e)

# ---------- Webhook endpoint ----------
@app.post(f"/{TELEGRAM_BOT_TOKEN}")
async def telegram_webhook(request: Request):
    if application is None:
        return JSONResponse({"ok": False, "error": "application not ready"}, status_code=503)
    body = await request.json()
    try:
        update = Update.de_json(body, application.bot)
        await application.update_queue.put(update)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.exception("Failed to process incoming update")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# ---------- Debug endpoints (safe for admin use) ----------
@app.get("/debug/webhookInfo")
async def debug_webhook_info():
    if application is None:
        return JSONResponse({"ok": False, "error": "application not ready"}, status_code=503)
    try:
        info = await application.bot.get_webhook_info()
        try:
            payload = info.to_dict()
        except Exception:
            payload = str(info)
        return JSONResponse({"ok": True, "webhook_info": payload})
    except Exception as e:
        logger.exception("debug/getWebhookInfo failed")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

@app.post("/debug/setWebhookManual")
async def debug_set_webhook_manual():
    if application is None:
        return JSONResponse({"ok": False, "error": "application not ready"}, status_code=503)
    webhook_endpoint = f"{WEBHOOK_URL.rstrip('/')}/{TELEGRAM_BOT_TOKEN}"
    try:
        await application.bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass
    try:
        resp = await application.bot.set_webhook(url=webhook_endpoint)
        logger.info("Manual set_webhook response: %s", resp)
        info = await application.bot.get_webhook_info()
        try:
            info_dict = info.to_dict()
        except Exception:
            info_dict = str(info)
        return JSONResponse({"ok": True, "set_response": resp, "webhook_info": info_dict})
    except Exception as e:
        logger.exception("Manual set_webhook failed")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)

# ---------- Health ----------
@app.get("/health")
async def health():
    webhook_endpoint = f"{WEBHOOK_URL.rstrip('/')}/{TELEGRAM_BOT_TOKEN}"
    status = "ready" if _ready else "starting"
    return JSONResponse({
        "status": status,
        "service": "SLH PROMO investors bot",
        "webhook": webhook_endpoint,
        "time": fmt_ts(datetime.now(timezone.utc))
    })
