import os
import time
from datetime import datetime, timezone

import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TD_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
CHECK_INTERVAL = max(int(os.getenv("CHECK_INTERVAL_SECONDS", "900")), 900)
COOLDOWN_MINUTES = int(os.getenv("SIGNAL_COOLDOWN_MINUTES", "60"))
SYMBOL = os.getenv("SYMBOL", "XAU/USD")

last_signal = {"side": None, "time": 0.0}
pending_signal = {"side": None, "count": 0}


def tg(method, **payload):
    if not TOKEN:
        return None
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    r = requests.post(url, data=payload, timeout=20)
    r.raise_for_status()
    return r.json()


def send(text):
    if not TOKEN or not CHAT_ID:
        print("[telegram-disabled]", text, flush=True)
        return False
    try:
        tg("sendMessage", chat_id=CHAT_ID, text=text, parse_mode="HTML", disable_web_page_preview="true")
        return True
    except Exception as e:
        print("Telegram send error:", repr(e), flush=True)
        return False


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
        raise RuntimeError("Twelve Data rate limit reached; waiting for quota reset")
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


def aggregate_h1(rows):
    usable = len(rows) - (len(rows) % 4)
    rows = rows[-usable:]
    out = []
    for i in range(0, len(rows), 4):
        g = rows[i:i + 4]
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


def macd(values):
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

    h1 = aggregate_h1(m15)
    if len(h1) < 55:
        raise RuntimeError("Not enough derived 1h data")

    c15 = [x["close"] for x in m15]
    c1h = [x["close"] for x in h1]
    price = c15[-1]
    e20 = ema(c15, 20)[-1]
    e50 = ema(c15, 50)[-1]
    h_e20 = ema(c1h, 20)[-1]
    h_e50 = ema(c1h, 50)[-1]
    rv = rsi(c15)
    mhist = macd(c15)
    av = atr(m15)

    buy_checks = [e20 > e50, h_e20 > h_e50, mhist > 0, 52 <= rv <= 68, price > e20]
    sell_checks = [e20 < e50, h_e20 < h_e50, mhist < 0, 32 <= rv <= 48, price < e20]

    buy_passed = sum(buy_checks)
    sell_passed = sum(sell_checks)
    side = "BUY" if buy_passed == 5 else "SELL" if sell_passed == 5 else "WAIT"

    if side == "BUY":
        sl, tp1, tp2 = price - 1.5 * av, price + 1.8 * av, price + 2.8 * av
    elif side == "SELL":
        sl, tp1, tp2 = price + 1.5 * av, price - 1.8 * av, price - 2.8 * av
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
    return (
        f"{emoji} <b>إشارة {ar} عالية الثقة — XAU/USD</b>\n"
        f"الدخول التقريبي: <b>{a['price']:.2f}</b>\n"
        f"وقف الخسارة: <b>{a['sl']:.2f}</b>\n"
        f"TP1: <b>{a['tp1']:.2f}</b>\n"
        f"TP2: <b>{a['tp2']:.2f}</b>\n"
        f"RSI: {a['rsi']:.1f} | ATR: {a['atr']:.2f}\n"
        "✅ الشروط الفنية 5/5 وثبت الاتجاه في فحصين متتاليين.\n"
        "⚠️ لا توجد صفقة مضمونة؛ التزم بإدارة المخاطر."
    )


def confirmed_signal(a):
    if a["side"] == "WAIT":
        pending_signal["side"] = None
        pending_signal["count"] = 0
        return False
    if pending_signal["side"] == a["side"]:
        pending_signal["count"] += 1
    else:
        pending_signal["side"] = a["side"]
        pending_signal["count"] = 1
    return pending_signal["count"] >= 2


def should_send_signal(a):
    if not confirmed_signal(a):
        return False
    now = time.time()
    if last_signal["side"] == a["side"] and now - last_signal["time"] < COOLDOWN_MINUTES * 60:
        return False
    last_signal["side"] = a["side"]
    last_signal["time"] = now
    pending_signal["count"] = 0
    return True


def main():
    print("Laith Gold Bot isolated high-confidence monitor started", flush=True)
    if not (TOKEN and CHAT_ID and TD_KEY):
        missing = [k for k, v in {
            "TELEGRAM_BOT_TOKEN": TOKEN,
            "TELEGRAM_CHAT_ID": CHAT_ID,
            "TWELVE_DATA_API_KEY": TD_KEY,
        }.items() if not v]
        raise RuntimeError("Missing Railway variables: " + ", ".join(missing))

    send("✅ <b>اختبار اتصال ناجح</b>\nبوت ليث الجديد شغال بشكل مستقل. لن يرسل صفقة إلا بعد تحقق شروط 5/5 مرتين متتاليتين.")

    while True:
        try:
            a = analyze()
            print("analysis", a, flush=True)
            if should_send_signal(a):
                send(format_signal(a))
        except Exception as e:
            print("monitor error:", repr(e), flush=True)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
