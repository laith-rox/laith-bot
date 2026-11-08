"""Experimental BTC M5 Telegram quick alerts, 19:00-23:00 Asia/Hebron.

Independent of conservative H1/H4 main signals and quarter-hour
NO-ENTRY research cards. Uses completed real BTC-USD spot candles only.
No trades, broker access, OpenAI usage or simulated fills.
"""
from datetime import timezone
from zoneinfo import ZoneInfo
import logging
import math

from engine import atr, ema, rsi
from market import DataError

LOG = logging.getLogger("laith.v4.btc.quick")
UTC = timezone.utc
LOCAL = ZoneInfo("Asia/Hebron")


def in_quick_window(now):
    if now.tzinfo is None:
        raise ValueError("btc_quick_requires_timezone")
    at = now.astimezone(LOCAL)
    return 19 <= at.hour < 23


def _float(value):
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise DataError("btc_quick_bad_number") from None
    if not math.isfinite(number):
        raise DataError("btc_quick_bad_number")
    return number


def _votes(bars, volumes):
    """Six independent observable checks; no artificial H4 sell preference."""
    if len(bars) < 75 or volumes is None or len(volumes) != len(bars):
        raise DataError("btc_quick_insufficient_history")
    tail = bars[-75:]
    if any((b.start - a.start).total_seconds() != 300 for a, b in zip(tail, tail[1:])):
        raise DataError("btc_quick_candle_gap")
    from v4_bitcoin_signals import _aggregate
    m15 = _aggregate(bars, 15)
    if len(m15) < 24:
        raise DataError("btc_quick_m15_insufficient")
    closes = [b.close for b in bars]
    f9, s21 = ema(closes, 9)[-1], ema(closes, 21)[-1]
    m15_closes = [b.close for b in m15]
    m15_9, m15_21 = ema(m15_closes, 9)[-1], ema(m15_closes, 21)[-1]
    recent = bars[-1]
    previous = bars[-2]
    span = max(1e-9, recent.high - recent.low)
    body_fraction = abs(recent.close - recent.open) / span
    m5_rsi = _float(rsi(closes[-70:]))
    values = [_float(x) for x in volumes[-21:]]
    if any(x < 0 for x in values):
        raise DataError("btc_quick_bad_volume")
    baseline = sum(values[:-1]) / 20
    if baseline <= 0:
        raise DataError("btc_quick_empty_volume")
    volume_ratio = values[-1] / baseline
    volatility = _float(atr(bars[-50:]))
    if volatility <= 0:
        raise DataError("btc_quick_zero_atr")
    return {
        "buy": [
            f9 > s21,
            m15_9 > m15_21,
            recent.close > recent.open and body_fraction >= .20,
            recent.close > previous.close,
            52 <= m5_rsi <= 78,
            volume_ratio >= .8,
        ],
        "sell": [
            f9 < s21,
            m15_9 < m15_21,
            recent.close < recent.open and body_fraction >= .20,
            recent.close < previous.close,
            22 <= m5_rsi <= 48,
            volume_ratio >= .8,
        ],
        "rsi": round(m5_rsi, 1),
        "volume_ratio": round(volume_ratio, 2),
        "atr5": volatility,
        "m15_bias": "BUY" if m15_9 > m15_21 else "SELL" if m15_9 < m15_21 else "WAIT",
        "last": recent,
    }


def analyze_quick(now, provider):
    """Return signal only for confirmed, current M5 setup; otherwise a clear WAIT."""
    if not in_quick_window(now):
        return {"status": "CLOSED", "reason": "outside_19_23_palestine"}
    bars = provider.candles(now, 5)
    if len(bars) < 75:
        raise DataError("btc_quick_insufficient_history")
    if not 0 <= (now - bars[-1].end).total_seconds() <= 150:
        raise DataError("btc_quick_candle_stale")
    ctx = _votes(bars, getattr(provider, "last_volumes", None))
    buy, sell = sum(ctx["buy"]), sum(ctx["sell"])
    last = ctx["last"]
    result = {
        "status": "WAIT", "reason": "btc_quick_conditions_not_met",
        "buy_score": buy, "sell_score": sell,
        "rsi": ctx["rsi"], "volume_ratio": ctx["volume_ratio"],
        "m15_bias": ctx["m15_bias"], "time": now.isoformat(),
        "candle_end": last.end.isoformat(),
    }
    # Require M5 EMA direction, M5 candle body and RSI, in addition to >=4/6.
    # H4 isn't a hard blocker for a quick trade, so counter-trend M5 is possible.
    buy_ok = (buy >= 4 and buy - sell >= 2 and
              ctx["buy"][0] and ctx["buy"][2] and ctx["buy"][4])
    sell_ok = (sell >= 4 and sell - buy >= 2 and
               ctx["sell"][0] and ctx["sell"][2] and ctx["sell"][4])
    if not (buy_ok or sell_ok):
        return result
    side = "BUY" if buy_ok else "SELL"
    volatility = ctx["atr5"]
    if (last.high - last.low) >= 3 * volatility:
        return dict(result, reason="btc_quick_spike")
    price = _float(provider.ticker(now))
    if price <= 0 or abs(price - last.close) > max(.40 * volatility, price * .0003):
        return dict(result, reason="btc_quick_price_chase")
    # Spot book snapshot supplies spread; no execution/broker access.
    book = provider.book()
    from v4_btc_quality import check_book
    depth = check_book(book, side)
    if depth["spread_bps"] > 8:
        return dict(result, reason="btc_quick_spread_wide")
    spread_cost = price * depth["spread_bps"] / 10000
    distance = 1.2 * volatility
    if distance <= 3 * spread_cost or volatility / price >= .025:
        return dict(result, reason="btc_quick_cost_or_volatility")
    sign = 1 if side == "BUY" else -1
    stop = price - sign * distance
    tp1 = price + sign * 1.5 * distance
    tp2 = price + sign * 2.2 * distance
    if min(stop, tp1, tp2) <= 0:
        return dict(result, reason="btc_quick_invalid_levels")
    # Snapshot imbalance is recorded as context, not used as directional magic.
    return {
        **result, "status": "SIGNAL", "reason": None, "side": side,
        "score": buy if buy_ok else sell,
        "entry": price, "sl": stop, "tp1": tp1, "tp2": tp2,
        "spread_bps": depth["spread_bps"],
        "book_imbalance": depth["imbalance"], "atr5": round(volatility, 2),
        "counter_m15": ctx["m15_bias"] != side,
    }


def message_quick(signal, now):
    local = now.astimezone(LOCAL)
    direction = "🟢 شراء BUY" if signal["side"] == "BUY" else "🔴 بيع SELL"
    period = "صباحًا" if local.hour < 12 else "مساءً"
    warning = "⚠️ الحركة عكس اتجاه M15؛ مخاطرة تصحيح قصيرة أعلى.\n" if signal["counter_m15"] else ""
    return (
        "₿ <b>BTC/USD — إشارة سريعة M5</b>\n"
        f"📍 <b>{direction}</b> | {signal['score']}/6 شروط\n"
        f"💵 دخول مرجعي Coinbase: <b>{signal['entry']:,.2f}$</b>\n"
        f"🛑 وقف مرجعي: <b>{signal['sl']:,.2f}$</b>\n"
        f"🎯 هدف 1: <b>{signal['tp1']:,.2f}$</b>\n"
        f"🎯 هدف 2: <b>{signal['tp2']:,.2f}$</b>\n"
        f"📊 شراء {signal['buy_score']}/6 | بيع {signal['sell_score']}/6"
        f" | RSI: {signal['rsi']} | حجم: {signal['volume_ratio']}×\n"
        f"🕔 شمعة M5 مغلقة: {signal['candle_end'][11:16]} UTC\n"
        f"🧭 M15: {signal['m15_bias']} | ATR M5: {signal['atr5']:,.2f}$\n"
        f"{warning}"
        f"🕘 {local.strftime('%I:%M')} {period} — فلسطين (19:00–23:00)\n"
        "📄 إشارة بحثية للمتابعة اليدوية فقط. Coinbase Spot ليس سعر JustMarkets؛ "
        "السبريد والرسوم الخاصة بوسيطك غير معروفة.\n"
        "⛔ لا تنفّذ تلقائيًا ولا تعتبر نجاح الصفقة مضمونًا."
    )


class BTCQuickPublisher:
    """Independent 5m scan, no order APIs, no reuse of the main BTC trade journal."""

    def __init__(self, store, notifier, provider=None):
        self.store = store
        self.notifier = notifier
        if provider is None:
            from v4_bitcoin_signals import CoinbaseBTC
            provider = CoinbaseBTC()
        self.provider = provider

    def cycle(self, now):
        if not in_quick_window(now):
            self.store.set("v4_btc_quick_status", {
                "status": "CLOSED", "reason": "outside_19_23_palestine",
                "time": now.isoformat(),
            })
            return "outside_hours"
        slot = int(now.timestamp() // 300)
        if self.store.get("v4_btc_quick_last_checked_slot") == slot:
            return "already_checked"
        try:
            result = analyze_quick(now, self.provider)
        except (DataError, ValueError) as exc:
            result = {"status": "WAIT_DATA", "reason": str(exc), "time": now.isoformat()}
            LOG.warning("btc_quick_wait_data reason=%s", exc)
        self.store.set("v4_btc_quick_last_checked_slot", slot)
        self.store.set("v4_btc_quick_status", result)
        LOG.info("btc_quick_check status=%s reason=%s buy=%s sell=%s",
                 result.get("status"), result.get("reason"), result.get("buy_score"),
                 result.get("sell_score"))
        if result["status"] != "SIGNAL":
            return "wait"
        # Do not spam repeated M5 messages in the same direction.
        same = self.store.get("v4_btc_quick_last_side") == result["side"]
        since = now.timestamp() - float(self.store.get("v4_btc_quick_last_at") or 0)
        if same and 0 <= since < 15 * 60:
            self.store.set("v4_btc_quick_status", {**result, "status": "COOLDOWN"})
            return "cooldown"
        try:
            sent = self.notifier is not None and self.notifier.send(message_quick(result, now)) is True
        except Exception:
            LOG.exception("btc_quick_delivery_exception")
            return "undelivered"
        if not sent:
            LOG.warning("btc_quick_delivery_failed")
            return "undelivered"
        self.store.set("v4_btc_quick_last_sent_slot", slot)
        self.store.set("v4_btc_quick_last_at", now.timestamp())
        self.store.set("v4_btc_quick_last_side", result["side"])
        LOG.info("btc_quick_signal_sent side=%s score=%s slot=%s",
                 result["side"], result["score"], slot)
        return "sent"
