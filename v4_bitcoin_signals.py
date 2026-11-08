"""Independent BTC-USD manual Telegram signal feed for experimental Laith V4.

Uses public Coinbase Exchange spot data only. No broker APIs or order execution.
BTC runs 24/7 independently of the gold broker-calendar gate.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import logging
import math
import os

import requests

from engine import atr, ema, rsi
from market import Bar, DataError, require_fresh
from v4_btc_quality import quality_gate
from v4_btc_followups import start_observation
from v4_btc_quarterly import weak_preview, quarterly_message

LOG = logging.getLogger("laith.v4.btc")
UTC = timezone.utc
PRODUCT = "BTC-USD"
URL = "https://api.exchange.coinbase.com/products/BTC-USD"
LOCAL = ZoneInfo("Asia/Hebron")


def _finite_positive(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise DataError("btc_invalid_number") from None
    if not math.isfinite(number) or number <= 0:
        raise DataError("btc_invalid_number")
    return number


def _bars(rows, minutes, now):
    if not isinstance(rows, list):
        raise DataError("btc_invalid_candles")
    unique = {}
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            raise DataError("btc_invalid_candles")
        stamp = _finite_positive(row[0])
        if stamp % (minutes * 60):
            raise DataError("btc_unaligned_candle")
        low, high, opened, closed = [_finite_positive(x) for x in row[1:5]]
        if not low <= min(opened, closed) <= max(opened, closed) <= high:
            raise DataError("btc_invalid_ohlc")
        bar = Bar(datetime.fromtimestamp(stamp, UTC), opened, high, low, closed, minutes)
        if stamp in unique and unique[stamp] != bar:
            raise DataError("btc_conflicting_candle")
        unique[stamp] = bar
    completed = sorted(
        (bar for bar in unique.values() if bar.end <= now - timedelta(seconds=10)),
        key=lambda bar: bar.start,
    )
    return completed


def _aggregate(bars, target_minutes):
    if not bars or target_minutes % bars[0].minutes:
        raise DataError("btc_aggregation_invalid")
    step = bars[0].minutes * 60
    width = target_minutes * 60
    groups = {}
    for bar in bars:
        slot = int(bar.start.timestamp()) // width * width
        groups.setdefault(slot, []).append(bar)
    result = []
    for slot, group in sorted(groups.items()):
        group.sort(key=lambda b: b.start)
        if [int(b.start.timestamp()) for b in group] != list(range(slot, slot + width, step)):
            continue
        result.append(Bar(
            datetime.fromtimestamp(slot, UTC),
            group[0].open,
            max(b.high for b in group),
            min(b.low for b in group),
            group[-1].close,
            target_minutes,
        ))
    return result


def _continuous_recent(bars, required):
    if len(bars) < required:
        raise DataError("btc_insufficient_history")
    tail = bars[-required:]
    step = tail[0].minutes * 60
    if any((b.start - a.start).total_seconds() != step for a, b in zip(tail, tail[1:])):
        raise DataError("btc_recent_data_gap")


class CoinbaseBTC:
    def __init__(self, session=None):
        self.session = session or requests.Session()

    def _get(self, path, **params):
        try:
            response = self.session.get(
                URL + path, params=params or None, timeout=(5, 15),
                headers={"User-Agent": "LaithV4-BTC-Signal-Research/1.0"},
            )
        except requests.RequestException:
            raise DataError("btc_connection_failed") from None
        if response.status_code != 200:
            raise DataError("btc_provider_unavailable")
        try:
            return response.json()
        except ValueError:
            raise DataError("btc_invalid_response") from None

    def candles(self, now, minutes):
        if minutes not in (5, 60):
            raise ValueError("btc_unsupported_interval")
        granularity = minutes * 60
        end = int(now.timestamp())
        start = end - 299 * granularity
        rows = self._get(
            "/candles", start=datetime.fromtimestamp(start, UTC).isoformat(),
            end=datetime.fromtimestamp(end, UTC).isoformat(),
            granularity=granularity,
        )
        bars = _bars(rows, minutes, now)
        if minutes == 5:
            volume_by_stamp = {}
            for row in rows:
                if isinstance(row, (list, tuple)) and len(row) >= 6:
                    try:
                        stamp, amount = int(float(row[0])), float(row[5])
                    except (TypeError, ValueError, OverflowError):
                        raise DataError("btc_volume_invalid") from None
                    if not math.isfinite(amount) or amount < 0:
                        raise DataError("btc_volume_invalid")
                    volume_by_stamp[stamp] = amount
            self.last_volumes = [volume_by_stamp.get(int(bar.start.timestamp())) for bar in bars]
        require_fresh(bars, now, 600 if minutes == 5 else 3900)
        _continuous_recent(bars, 24 if minutes == 5 else 60)
        if minutes == 5:
            self.last_5m_bars = bars
        return bars

    def ticker(self, now):
        payload = self._get("/ticker")
        if not isinstance(payload, dict):
            raise DataError("btc_invalid_quote")
        price = _finite_positive(payload.get("price"))
        try:
            dt = datetime.fromisoformat(str(payload["time"]).replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError):
            raise DataError("btc_invalid_quote_time") from None
        if dt.tzinfo is None or not 0 <= (now - dt.astimezone(UTC)).total_seconds() <= 90:
            raise DataError("btc_quote_stale")
        return price

    def book(self):
        """Read-only top-15 market depth snapshot."""
        return self._get("/book", level=2)

    def derivatives(self):
        """Separate Binance BTCUSDT perpetual context; unavailable is not zero."""
        base = "https://fapi.binance.com"
        def get(path, params):
            try:
                response = self.session.get(base + path, params=params, timeout=(4, 8))
                if response.status_code != 200:
                    raise DataError("btc_futures_source_unavailable")
                return response.json()
            except (requests.RequestException, ValueError):
                raise DataError("btc_futures_source_unavailable") from None
        try:
            funding = get("/fapi/v1/premiumIndex", {"symbol": "BTCUSDT"})
            history = get("/futures/data/openInterestHist",
                          {"symbol": "BTCUSDT", "period": "5m", "limit": 3})
            if not isinstance(funding, dict) or not isinstance(history, list) or len(history) < 2:
                return {"available": False}
            return {
                "available": True, "funding": funding["lastFundingRate"],
                "open_interest": history[-1]["sumOpenInterest"],
                "previous_open_interest": history[-2]["sumOpenInterest"],
                "timestamp": min(float(funding["time"]), float(history[-1]["timestamp"])) / 1000.,
            }
        except (DataError, TypeError, KeyError, ValueError, OverflowError):
            return {"available": False}


def _trend(bars):
    values = [bar.close for bar in bars]
    if len(values) < 55:
        raise DataError("btc_insufficient_trend_history")
    fast, slow = ema(values, 20), ema(values, 50)
    if fast[-1] > slow[-1] and fast[-1] > fast[-4]:
        return "BUY"
    if fast[-1] < slow[-1] and fast[-1] < fast[-4]:
        return "SELL"
    return "WAIT"


def analyze_btc(now, provider):
    """Return a qualifying manual signal or a clear WAIT result; never an order."""
    m5 = provider.candles(now, 5)
    h1 = provider.candles(now, 60)
    m15, h4 = _aggregate(m5, 15), _aggregate(h1, 240)
    _continuous_recent(m15, 30)
    _continuous_recent(h4, 55)
    if (now - m15[-1].end).total_seconds() > 1200:
        raise DataError("btc_m15_stale")
    if (now - h4[-1].end).total_seconds() > 4 * 3600 + 300:
        raise DataError("btc_h4_stale")

    direction = _trend(h1)
    four_hour_trend = _trend(h4)
    trend_context = {"h1_trend": direction, "h4_trend": four_hour_trend,
                     "bias": direction if direction == four_hour_trend and direction != "WAIT" else "WAIT",
                     "time": now.isoformat()}
    if direction == "WAIT" or four_hour_trend != direction:
        return {"status": "WAIT", "reason": "h1_h4_not_aligned", **trend_context}
    price = provider.ticker(now)
    volatility = atr(m15[-40:])
    if abs(price - m5[-1].close) > max(0.6 * volatility, price * 0.0015):
        return {"status": "WAIT", "reason": "btc_price_moved_too_far", **trend_context}
    m15_fast = ema([b.close for b in m15], 20)[-1]
    m15_slow = ema([b.close for b in m15], 50)[-1]
    five_rsi = rsi([b.close for b in m5[-70:]])
    recent = m15[-9:-1]
    local_high = max(b.high for b in recent)
    local_low = min(b.low for b in recent)
    last15, last5 = m15[-1], m5[-1]
    up = direction == "BUY"
    confirmation = (
        (last15.close > local_high + 0.1 * volatility or
         (last15.low <= m15_fast and last15.close > m15_fast))
        if up else
        (last15.close < local_low - 0.1 * volatility or
         (last15.high >= m15_fast and last15.close < m15_fast))
    )
    checks = [
        True,  # H1 direction, mandatory
        True,  # H4 direction, mandatory
        (m15_fast > m15_slow) if up else (m15_fast < m15_slow),
        (last15.close > last15.open) if up else (last15.close < last15.open),
        (last5.close > last5.open) if up else (last5.close < last5.open),
        (48 <= five_rsi <= 72) if up else (28 <= five_rsi <= 52),
        confirmation,
    ]
    score = sum(checks)
    if score < 6 or not confirmation:
        return {"status": "WAIT", "reason": "btc_conditions_not_met", "score": score,
                **trend_context}

    quality = quality_gate(
        now, direction, price, m5, m15, volatility,
        getattr(provider, "last_volumes", None), provider.book(), provider.derivatives(),
    )
    if quality["status"] != "OK":
        return {"status": quality["status"], "reason": quality.get("reason"), "score": score,
                **trend_context}
    midpoint = (quality["book"]["bid"] + quality["book"]["ask"]) / 2
    if abs(midpoint - price) / midpoint > .001:
        return {"status": "WAIT", "reason": "btc_quote_orderbook_mismatch", "score": score,
                **trend_context}
    risk = quality["risk"]
    return {
        "status": "SIGNAL", "side": direction, "score": score,
        **trend_context,
        "entry": price, "sl": risk["sl"], "tp1": risk["tp1"], "tp2": risk["tp2"],
        "atr15": volatility, "time": now.isoformat(),
        "liquidity": quality["liquidity"],
        "volume_ratio": quality["volume"]["ratio"],
        "spot_spread_bps": quality["book"]["spread_bps"],
        "derivatives": quality["derivatives"],
        "session": quality["session"],
        "rr_reference": risk["rr_reference"],
        "risk_distance": risk["sl_distance"],
        "volatility_regime": risk["volatility_regime"],
    }


def _message(signal, now):
    side = "🟢 شراء BUY" if signal["side"] == "BUY" else "🔴 بيع SELL"
    clock = now.astimezone(LOCAL)
    hour = clock.strftime("%I:%M")
    period = "صباحًا" if clock.hour < 12 else "مساءً"
    derivatives = signal.get("derivatives") or {}
    context = "بيانات العقود: متاحة" if derivatives.get("available") else "بيانات العقود: غير متاحة"
    return (
        "₿ <b>إشارة بيتكوين مستقلة — BTC/USD</b>\n"
        f"الاتجاه: <b>{side}</b>\n"
        f"📍 الدخول المرجعي: <b>{signal['entry']:,.2f}$</b>\n"
        f"🛑 وقف الخسارة: <b>{signal['sl']:,.2f}$</b>\n"
        f"🎯 الهدف الأول: <b>{signal['tp1']:,.2f}$</b>\n"
        f"🎯 الهدف الثاني: <b>{signal['tp2']:,.2f}$</b>\n"
        f"🧠 الشروط: {signal['score']}/7 | H4 + H1 + M15 + M5\n"
        f"🌊 السيولة: {('سحب سيولة' if (signal.get('liquidity') or {}).get('liquidity_sweep') else 'تأكيد نطاق')}\n"
        f"📊 الحجم: {signal.get('volume_ratio', '—')}× | السبريد الفوري: {signal.get('spot_spread_bps', '—')} نقطة أساس\n"
        f"⚖️ العائد/المخاطرة المرجعي: {signal.get('rr_reference', '—')} | تذبذب: {signal.get('volatility_regime', '—')}\n"
        f"🕘 الجلسة: {signal.get('session', '—')} | {context}\n"        f"🕒 {hour} {period} — توقيت فلسطين\n"
        "📊 أسعار Coinbase الفورية، وقد تختلف عن BTCUSD في JustMarkets؛ سبريد ورسوم الوسيط غير متحققين.\n"
        "📄 تنبيه يدوي فقط، بدون فتح صفقات أو ضمان للربح."
    )


class BitcoinSignalPublisher:
    def __init__(self, store, notifier, provider=None):
        self.store = store
        self.notifier = notifier
        self.provider = provider or CoinbaseBTC()

    def _quarterly_enabled(self):
        return os.getenv("V4_BTC_QUARTERLY_REPORTS_ENABLED") == "1"

    def _quarterly_report(self, now, slot, state, note=None):
        """At most one NO-ENTRY research card per 15m slot; never a paper trade."""
        if self.store.get("v4_btc_quarterly_last_slot") == slot:
            return "already_sent"
        preview = weak_preview(now, self.provider, state, _aggregate)
        # An actionably qualified candidate in cooldown is NOT a weak setup.
        # Keep it labelled NO ENTRY without inventing fake signal statistics.
        if state.get("status") == "SIGNAL":
            preview = {
                "side": state.get("side", "WAIT"),
                "score": state.get("score"), "price": None,
            }
        message = quarterly_message(now, state, preview, note=note)
        try:
            delivered = self.notifier is not None and self.notifier.send(message) is True
        except Exception:
            LOG.exception("btc_quarterly_telegram_error")
            return "undelivered"
        if not delivered:
            LOG.warning("btc_quarterly_delivery_failed slot=%s", slot)
            return "undelivered"
        self.store.set("v4_btc_quarterly_last_slot", slot)
        self.store.set("v4_btc_quarterly_last", {
            "slot": slot, "time": now.isoformat(), "status": state.get("status"),
            "reason": state.get("reason"), "side": preview.get("side"),
            "score": preview.get("score"), "no_entry": True,
        })
        LOG.info("btc_quarterly_no_entry_sent slot=%s score=%s side=%s reason=%s",
                 slot, preview.get("score"), preview.get("side"), state.get("reason"))
        return "weak_sent"

    def cycle(self, now):
        if now.tzinfo is None:
            raise ValueError("btc_requires_timezone_aware_now")
        slot = int(now.timestamp() // 900)
        if self.store.get("v4_btc_last_sent_slot") == slot:
            return "already_sent"
        if self._quarterly_enabled() and self.store.get("v4_btc_quarterly_last_slot") == slot:
            return "already_sent"
        try:
            signal = analyze_btc(now, self.provider)
        except DataError as exc:
            self.store.set("v4_btc_status", {
                "status": "WAIT_DATA", "reason": str(exc),
                "time": now.isoformat(), "bias": "WAIT",
            })
            LOG.warning("btc_feed_wait reason=%s", exc)
            if self._quarterly_enabled():
                return self._quarterly_report(now, slot, self.store.get("v4_btc_status"))
            return "wait_data"
        self.store.set("v4_btc_status", signal)
        LOG.info("btc_signal_check status=%s reason=%s score=%s", signal.get("status"), signal.get("reason"), signal.get("score"))
        if signal["status"] != "SIGNAL":
            if self._quarterly_enabled():
                return self._quarterly_report(now, slot, signal)
            return "wait"
        last_time = float(self.store.get("v4_btc_last_sent_at") or 0)
        last_side = self.store.get("v4_btc_last_sent_side")
        if last_side == signal["side"] and now.timestamp() - last_time < 45 * 60:
            if self._quarterly_enabled():
                return self._quarterly_report(now, slot, signal, note="cooldown")
            return "cooldown"
        # One unresolved BTC observation at a time; this never blocks gold.
        active = self.store.get("v4_btc_observed_active") or {}
        if active.get("status") == "OPEN":
            if self._quarterly_enabled():
                return self._quarterly_report(now, slot, signal, note="active_observation")
            return "active_observation"
        # Last-second live reference guard before Telegram publishing.
        if hasattr(self.provider, "ticker") and abs((datetime.now(UTC) - now).total_seconds()) < 90:
            try:
                current_price = self.provider.ticker(datetime.now(UTC))
            except DataError:
                if self._quarterly_enabled():
                    return self._quarterly_report(now, slot, {"status": "WAIT_DATA", "reason": "btc_quote_stale", "time": now.isoformat()})
                return "wait_data"
            if abs(current_price - signal["entry"]) > .25 * abs(signal["entry"] - signal["sl"]):
                if self._quarterly_enabled():
                    return self._quarterly_report(now, slot, signal, note="price_moved")
                return "price_moved"
        if self.notifier and self.notifier.send(_message(signal, now)) is True:
            self.store.set("v4_btc_last_sent_slot", slot)
            self.store.set("v4_btc_last_sent_at", now.timestamp())
            self.store.set("v4_btc_last_sent_side", signal["side"])
            start_observation(self.store, signal, now)
            LOG.info("btc_signal_sent side=%s score=%s slot=%s", signal["side"], signal["score"], slot)
            return "sent"
        LOG.warning("btc_signal_delivery_failed")
        return "undelivered"
