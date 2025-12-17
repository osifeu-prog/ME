import os
import logging
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import yfinance as yf
import ccxt

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ---------- Env ----------
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DEFAULT_EXCHANGE = os.getenv("DEFAULT_EXCHANGE", "binance")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

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

# ---------- FastAPI ----------
app = FastAPI(title="Trade Bot Service")
application: Application | None = None

# ---------- Utils ----------
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

# ---------- CCXT ----------
def get_exchange(name: str = DEFAULT_EXCHANGE):
    ex_class = getattr(ccxt, name)
    return ex_class({"enableRateLimit": True, "timeout": 10000})

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

# ---------- Telegram Handlers ----------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ברוך הבא לבוט נתוני שוק.\n\n"
        "פקודות:\n"
        "/price <symbol>\n"
        "/ohlcv <symbol> <timeframe>\n"
        "/indicators <symbol>\n"
        "/correlate <symbols...>\n"
        "/help\n\n"
        "המידע לצורכי אינפורמציה בלבד."
    )
    await update.message.reply_text(text)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_cmd(update, context)

async def price_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("שימוש: /price <symbol>")
        return
    symbol = normalize_symbol_for_exchange(context.args[0])
    try:
        t = await ccxt_ticker(symbol)
        price = safe_float(t.get("last"))
        ts = t.get("datetime") or fmt_ts(datetime.now(timezone.utc))
        text = f"{symbol} מחיר אחרון: {price}\nזמן: {ts}"
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"שגיאה: {e}")

async def ohlcv_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("שימוש: /ohlcv <symbol> <timeframe>")
        return
    symbol = normalize_symbol_for_exchange(context.args[0])
    timeframe = context.args[1] if len(context.args) > 1 else "1m"
    try:
        df = await ccxt_ohlcv(symbol, timeframe=timeframe, limit=50)
        last = df.iloc[-1]
        text = f"{symbol} {timeframe}\nפתיחה: {last['open']} סגירה: {last['close']}"
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"שגיאה: {e}")

async def indicators_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("שימוש: /indicators <symbol>")
        return
    symbol = normalize_symbol_for_exchange(context.args[0])
    df = await ccxt_ohlcv(symbol, timeframe="1m", limit=200)
    closes = df["close"]
    sma20 = sma(closes, 20).iloc[-1]
    rsi14 = rsi(closes, 14).iloc[-1]
    await update.message.reply_text(f"{symbol}\nSMA20: {sma20:.2f}\nRSI14: {rsi14:.2f}")

async def correlate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("שימוש: /correlate <symbol1> <symbol2>")
        return
    corr, ts = compute_correlation(context.args)
    if corr is None:
        await update.message.reply_text("אין נתונים.")
        return
    lines = [f"{i}: " + " | ".join(f"{corr.loc[i,j]:.2f}" for j in corr.columns) for i in corr.index]
    await update.message.reply_text("\n".join(lines))

# ---------- Bot init ----------
def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("price", price_cmd))
    app.add_handler(CommandHandler("ohlcv", ohlcv_cmd))
    app.add_handler(CommandHandler("indicators", indicators_cmd))
    app.add_handler(CommandHandler("correlate", correlate_cmd))
    return app

# ---------- FastAPI lifecycle ----------
@app.on_event("startup")
async def on_startup():
    global application
    application = build_application()
    # קובע webhook מול טלגרם
    await application.bot.set_web
