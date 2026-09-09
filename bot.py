import os
import time
from datetime import datetime, timezone, time as dt_time
from zoneinfo import ZoneInfo

import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TD_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
CHECK_INTERVAL = max(int(os.getenv("CHECK_INTERVAL_SECONDS", "300")), 300)
COOLDOWN_MINUTES = max(int(os.getenv("SIGNAL_COOLDOWN_MINUTES", "60")), 60)
SYMBOL = os.getenv("SYMBOL", "XAU/USD")
LOCAL_TZ = ZoneInfo("Asia/Hebron")
START_TIME = dt_time(4, 30)
END_TIME = dt_time(23, 30)

last_signal = {"side": None, "time": 0.0}


def tg(method, **payload):
    if not TOKEN:
        return None
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    r = requests.post(url, data=payload, timeout=20)
    r.raise_for_status()
    return r.json()


def send(text):
    if not TOKEN or not CHAT_ID:
        print("[telegram-disabled]", flush=True)
        return False
    try:
        tg("sendMessage", chat_id=CHAT_ID, text=text, parse_mode="HTML", disable_web_page_preview="true")
        return True
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", "unknown")
        print(f"Telegram send HTTP error: {code}", flush=True)
        return False
    except Exception as e:
        print(f"Telegram send error: {type(e).__name__}", flush=True)
        return False


def in_trading_window():
    now = datetime.now(LOCAL_TZ).time()
    return START_TIME <= now <= END_TIME


def fetch_m15(outputsize=240):
    if not TD_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY is missing")
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": SYMBOL,
            "interval": "15min",
            "outputsize": outputsize,
            "apikey": TD_KEY,
            "format": "JSON",
        },
        timeout=20,
    )
    if r.status_code == 429:
        raise RuntimeError("Twelve Data quota/rate limit reached")
    r.raise_for_status()
    data = r.json()
    if data.get("status") == "error" or "values" not in data:
        raise RuntimeError(data.get("message") or "Bad Twelve Data response")
    rows = []
    for x in reversed(data["values"]):
        rows.append({
            "datetime": x["datetime"],
            "open": float(x["open"]),
            "high": float(x["high"]),
            "low": float(x["low"]),
            "close": float(x["close"]),
        })
    if len(rows) < 220:
        raise RuntimeError(f"Not enough market data: {len(rows)} bars")
    return rows


def aggregate(rows, group_size):
    usable = len(rows) - (len(rows) % group_size)
    rows = rows[-usable:]
    out = []
    for i in range(0, len(rows), group_size):
        g = rows[i:i + group_size]
        out.append({
            "datetime": g[-1]["datetime"],
            "open": g[0]["open"],
            "high": max(x["high"] for x in g),
            "low": min(x["low"] for x in g),
            "close": g[-1]["close"],
        })
    return out


def ema(values, period):
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(values, period=14):
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0 if ag > 0 else 50.0
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)


def atr(rows, period=14):
    trs = []
    for i in range(1, len(rows)):
        h, l, pc = rows[i]["high"], rows[i]["low"], rows[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    a = sum(trs[:period]) / period
    for tr in trs[period:]:
        a = (a * (period - 1) + tr) / period
    return a


def macd_hist(values):
    e12 = ema(values, 12)
    e26 = ema(values, 26)
    line = [a - b for a, b in zip(e12, e26)]
    signal = ema(line, 9)
    return line[-1] - signal[-1]


def freshness_ok(rows):
    dt = datetime.fromisoformat(rows[-1]["datetime"].replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 60.0
    return age <= 45, age


def analyze():
    m15 = fetch_m15()
    fresh, age = freshness_ok(m15)
    if not fresh:
        raise RuntimeError(f"Stale data: {age:.1f} minutes")

    h1 = aggregate(m15, 4)
    if len(h1) < 55:
        raise RuntimeError("Not enough derived 1h data")

    c15 = [x["close"] for x in m15]
    c1h = [x["close"] for x in h1]
    price = c15[-1]
    e20 = ema(c15, 20)[-1]
    e50 = ema(c15, 50)[-1]
    h1e20 = ema(c1h, 20)[-1]
    h1e50 = ema(c1h, 50)[-1]
    rv = rsi(c15)
    mhist = macd_hist(c15)
    av = atr(m15)
    candle = m15[-1]
    bullish_candle = candle["close"] > candle["open"]
    bearish_candle = candle["close"] < candle["open"]
    not_extended = abs(price - e20) <= 1.5 * av

    buy_checks = [
        e20 > e50,
        h1e20 > h1e50,
        mhist > 0,
        51 <= rv <= 69,
        price > e20,
        bullish_candle,
        not_extended,
    ]
    sell_checks = [
        e20 < e50,
        h1e20 < h1e50,
        mhist < 0,
        31 <= rv <= 49,
        price < e20,
        bearish_candle,
        not_extended,
    ]

    buy_passed = sum(buy_checks)
    sell_passed = sum(sell_checks)

    # Balanced mode: 6/7 is enough, but higher-timeframe trend is mandatory.
    buy_core = buy_checks[0] and buy_checks[1] and buy_checks[4]
    sell_core = sell_checks[0] and sell_checks[1] and sell_checks[4]
    side = "BUY" if buy_passed >= 6 and buy_core else "SELL" if sell_passed >= 6 and sell_core else "WAIT"

    if side == "BUY":
        sl, tp1, tp2 = price - 1.4 * av, price + 1.8 * av, price + 2.6 * av
    elif side == "SELL":
        sl, tp1, tp2 = price + 1.4 * av, price - 1.8 * av, price - 2.6 * av
    else:
        sl = tp1 = tp2 = None

    return {
        "side": side, "price": price, "rsi": rv, "atr": av,
        "sl": sl, "tp1": tp1, "tp2": tp2,
        "buy_passed": buy_passed, "sell_passed": sell_passed,
    }


def format_signal(a):
    emoji = "🟢" if a["side"] == "BUY" else "🔴"
    ar = "شراء" if a["side"] == "BUY" else "بيع"
    passed = a["buy_passed"] if a["side"] == "BUY" else a["sell_passed"]
    return (
        f"{emoji} <b>إشارة {ar} قوية — XAU/USD</b>\n"
        f"الدخول التقريبي: <b>{a['price']:.2f}</b>\n"
        f"وقف الخسارة: <b>{a['sl']:.2f}</b>\n"
        f"TP1: <b>{a['tp1']:.2f}</b>\n"
        f"TP2: <b>{a['tp2']:.2f}</b>\n"
        f"RSI: {a['rsi']:.1f} | ATR: {a['atr']:.2f}\n"
        f"✅ تحقق {passed}/7 مع توافق اتجاه 15د + 1س.\n"
        "⚠️ فلترة قوية وليست ضمان ربح أو نسبة نجاح ثابتة."
    )


def should_send_signal(a):
    if a["side"] == "WAIT":
        return False
    now = time.time()
    if last_signal["side"] == a["side"] and now - last_signal["time"] < COOLDOWN_MINUTES * 60:
        return False
    last_signal["side"] = a["side"]
    last_signal["time"] = now
    return True


def main():
    print("Laith Gold Bot balanced high-confidence monitor started", flush=True)
    if not (TOKEN and CHAT_ID and TD_KEY):
        missing = [k for k, v in {
            "TELEGRAM_BOT_TOKEN": TOKEN,
            "TELEGRAM_CHAT_ID": CHAT_ID,
            "TWELVE_DATA_API_KEY": TD_KEY,
        }.items() if not v]
        raise RuntimeError("Missing Railway variables: " + ", ".join(missing))

    send("✅ <b>بوت ليث جاهز</b>\nالوضع المتوازن مفعل: فحص كل 5 دقائق، دخول من أول تحقق قوي، وساعات العمل 04:30–23:30 بتوقيت فلسطين.")

    while True:
        if not in_trading_window():
            time.sleep(60)
            continue
        try:
            a = analyze()
            print("analysis", {"side": a["side"], "buy": a["buy_passed"], "sell": a["sell_passed"]}, flush=True)
            if should_send_signal(a):
                send(format_signal(a))
        except Exception as e:
            print(f"monitor error: {type(e).__name__}: {e}", flush=True)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
