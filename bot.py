import os
import time
import math
import threading
from datetime import datetime, timezone

import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TD_KEY = os.getenv("TWELVE_DATA_API_KEY", "").strip()
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SECONDS", "300"))
COOLDOWN_MINUTES = int(os.getenv("SIGNAL_COOLDOWN_MINUTES", "45"))
SYMBOL = os.getenv("SYMBOL", "XAU/USD")

last_signal = {"side": None, "time": 0.0}
stop_event = threading.Event()


def tg(method, **payload):
    if not TOKEN:
        return None
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    r = requests.post(url, data=payload, timeout=25)
    r.raise_for_status()
    return r.json()


def send(text, chat_id=None):
    cid = str(chat_id or CHAT_ID).strip()
    if not TOKEN or not cid:
        print("[telegram-disabled]", text, flush=True)
        return
    try:
        tg("sendMessage", chat_id=cid, text=text, parse_mode="HTML", disable_web_page_preview="true")
    except Exception as e:
        print("Telegram send error:", repr(e), flush=True)


def fetch_series(interval, outputsize=160):
    if not TD_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY is missing")
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": SYMBOL,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": TD_KEY,
            "format": "JSON",
        },
        timeout=25,
    )
    r.raise_for_status()
    data = r.json()
    if data.get("status") == "error" or "values" not in data:
        raise RuntimeError(data.get("message") or f"Bad Twelve Data response: {data}")
    rows = []
    for x in reversed(data["values"]):
        rows.append({
            "datetime": x["datetime"],
            "open": float(x["open"]),
            "high": float(x["high"]),
            "low": float(x["low"]),
            "close": float(x["close"]),
        })
    if len(rows) < 60:
        raise RuntimeError(f"Not enough market data: {len(rows)} bars")
    return rows


def ema(values, period):
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(values, period=14):
    if len(values) <= period:
        return 50.0
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
    return 100.0 - (100.0 / (1.0 + rs))


def atr(rows, period=14):
    trs = []
    for i in range(1, len(rows)):
        h, l, pc = rows[i]["high"], rows[i]["low"], rows[i-1]["close"]
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    if len(trs) < period:
        return sum(trs) / max(len(trs), 1)
    a = sum(trs[:period]) / period
    for tr in trs[period:]:
        a = (a * (period - 1) + tr) / period
    return a


def macd(values):
    e12 = ema(values, 12)
    e26 = ema(values, 26)
    line = [a-b for a, b in zip(e12, e26)]
    signal = ema(line, 9)
    return line[-1], signal[-1], line[-1] - signal[-1]


def freshness_ok(rows, interval_minutes):
    try:
        dt = datetime.fromisoformat(rows[-1]["datetime"].replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 60.0
        return age <= max(interval_minutes * 3, 20), age
    except Exception:
        return True, None


def analyze():
    m15 = fetch_series("15min")
    h1 = fetch_series("1h")
    ok15, age15 = freshness_ok(m15, 15)
    ok1h, age1h = freshness_ok(h1, 60)
    if not ok15 or not ok1h:
        raise RuntimeError(f"Stale data (15m={age15}, 1h={age1h} minutes)")

    c15 = [x["close"] for x in m15]
    c1h = [x["close"] for x in h1]
    price = c15[-1]
    e20 = ema(c15, 20)[-1]
    e50 = ema(c15, 50)[-1]
    h_e20 = ema(c1h, 20)[-1]
    h_e50 = ema(c1h, 50)[-1]
    rv = rsi(c15)
    mline, msignal, mhist = macd(c15)
    av = atr(m15)

    buy_score = 0
    sell_score = 0
    reasons = []

    if e20 > e50:
        buy_score += 2; reasons.append("15د اتجاه صاعد")
    else:
        sell_score += 2; reasons.append("15د اتجاه هابط")
    if h_e20 > h_e50:
        buy_score += 3; reasons.append("1س داعم للصعود")
    else:
        sell_score += 3; reasons.append("1س داعم للهبوط")
    if mhist > 0:
        buy_score += 1
    else:
        sell_score += 1
    if 52 <= rv <= 72:
        buy_score += 1
    elif 28 <= rv <= 48:
        sell_score += 1
    if price > e20:
        buy_score += 1
    else:
        sell_score += 1

    side = "WAIT"
    if buy_score >= 6 and buy_score - sell_score >= 3:
        side = "BUY"
    elif sell_score >= 6 and sell_score - buy_score >= 3:
        side = "SELL"

    if side == "BUY":
        sl = price - 1.6 * av
        tp1 = price + 1.6 * av
        tp2 = price + 2.6 * av
    elif side == "SELL":
        sl = price + 1.6 * av
        tp1 = price - 1.6 * av
        tp2 = price - 2.6 * av
    else:
        sl = tp1 = tp2 = None

    return {
        "side": side, "price": price, "rsi": rv, "atr": av,
        "buy_score": buy_score, "sell_score": sell_score,
        "sl": sl, "tp1": tp1, "tp2": tp2,
        "reasons": reasons,
    }


def format_analysis(a, manual=False):
    if a["side"] == "WAIT":
        return (
            f"🟡 <b>لا دخول الآن — XAU/USD</b>\n"
            f"السعر: <b>{a['price']:.2f}</b>\n"
            f"RSI: {a['rsi']:.1f}\n"
            f"شراء {a['buy_score']} | بيع {a['sell_score']}\n"
            "السبب: الإشارات غير متفقة بما يكفي."
        )
    emoji = "🟢" if a["side"] == "BUY" else "🔴"
    ar = "شراء" if a["side"] == "BUY" else "بيع"
    return (
        f"{emoji} <b>إشارة {ar} — XAU/USD</b>\n"
        f"الدخول التقريبي: <b>{a['price']:.2f}</b>\n"
        f"وقف الخسارة: <b>{a['sl']:.2f}</b>\n"
        f"TP1: <b>{a['tp1']:.2f}</b>\n"
        f"TP2: <b>{a['tp2']:.2f}</b>\n"
        f"RSI: {a['rsi']:.1f} | ATR: {a['atr']:.2f}\n"
        f"قوة: شراء {a['buy_score']} | بيع {a['sell_score']}\n"
        "⚠️ إدارة المخاطر إلزامية؛ الإشارة تحليل وليست ضمانًا."
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


def monitor_loop():
    print("Laith Gold Bot monitor started", flush=True)
    while not stop_event.is_set():
        if not (TOKEN and CHAT_ID and TD_KEY):
            missing = [k for k, v in {
                "TELEGRAM_BOT_TOKEN": TOKEN,
                "TELEGRAM_CHAT_ID": CHAT_ID,
                "TWELVE_DATA_API_KEY": TD_KEY,
            }.items() if not v]
            print("Waiting for Railway variables:", ", ".join(missing), flush=True)
            stop_event.wait(30)
            continue
        try:
            a = analyze()
            print("analysis", a, flush=True)
            if should_send_signal(a):
                send(format_analysis(a))
        except Exception as e:
            print("monitor error:", repr(e), flush=True)
        stop_event.wait(CHECK_INTERVAL)


def polling_loop():
    if not TOKEN:
        print("Telegram polling disabled until token is configured", flush=True)
        return
    offset = None
    while not stop_event.is_set():
        try:
            payload = {"timeout": 25, "allowed_updates": '["message"]'}
            if offset is not None:
                payload["offset"] = offset
            data = tg("getUpdates", **payload) or {}
            for u in data.get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                text = (msg.get("text") or "").strip().lower()
                cid = msg.get("chat", {}).get("id")
                if not cid:
                    continue
                if text in ("/start", "start"):
                    send("🟡 <b>بوت ليث للذهب شغال</b>\nاكتب /status لتحليل فوري.", cid)
                elif text in ("/status", "/signal", "حلل", "تحليل"):
                    try:
                        send(format_analysis(analyze(), manual=True), cid)
                    except Exception as e:
                        send(f"⚠️ تعذر جلب بيانات سليمة الآن: {e}", cid)
        except Exception as e:
            print("polling error:", repr(e), flush=True)
            time.sleep(5)


if __name__ == "__main__":
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    polling_loop()
    t.join()
