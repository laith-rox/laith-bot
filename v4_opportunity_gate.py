"""Opportunity-driven paper signal gate. No order execution or scheduling changes."""


def evaluate_opportunity(decision, reference, cached_market=False, news_clear=True):
    q = (decision or {}).get("quick5m") or {}
    side = q.get("side")
    if side not in ("BUY", "SELL") or not q.get("entry_allowed"):
        return False, "no_confirmed_direction"
    if not reference.get("timing_aligned") or reference.get("delayed_reference"):
        return False, "live_price_unverified"
    if not reference.get("current_five_minute_candle") or cached_market:
        return False, "market_data_not_live"
    if not news_clear:
        return False, "news_risk"
    score = int(q.get(side.lower(), 0))
    if score < 6:
        return False, "weak_setup"
    if q.get("higher_side") != side:
        return False, "higher_timeframe_conflict"
    atr = float(q.get("atr5") or 0)
    price = float(q.get("current_price") or 0)
    candle_open = float(q.get("current_open") or 0)
    if atr <= 0 or price <= 0:
        return False, "invalid_volatility_or_price"
    if abs(price - candle_open) > 0.35 * atr:
        return False, "late_entry_after_impulse"
    return True, "confirmed_opportunity"
