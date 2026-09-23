"""Adaptive XAU/USD decision layer for the isolated DEMO bridge.

Pure decision logic only: no broker/network actions. Designed so each regime can
be backtested before it is allowed to publish orders.
"""
from dataclasses import dataclass
from typing import Sequence

@dataclass(frozen=True)
class Decision:
    mode: str
    side: str | None
    confidence: int
    risk_mult: float
    stop_atr: float
    target_r: float
    reason: str

def decide(*, buy_score:int, sell_score:int, rsi:float, atr:float,
           atr_baseline:float, ema_fast:float, ema_slow:float,
           close:float, recent_high:float, recent_low:float,
           momentum:float, hour_local:int) -> Decision:
    """Classify regime then choose SNIPER / MAIN / WAIT.

    Night hours do not automatically increase size. Higher risk_mult is allowed
    only for unusually strong, aligned evidence; execution layer still enforces
    DEMO-only and its hard risk ceiling.
    """
    if atr <= 0 or atr_baseline <= 0:
        return Decision("WAIT", None, 0, 0.0, 0.0, 0.0, "bad_volatility")

    vol_ratio = atr / atr_baseline
    trend_up = ema_fast > ema_slow
    trend_dn = ema_fast < ema_slow
    break_up = close > recent_high
    break_dn = close < recent_low
    mom_up = momentum > 0
    mom_dn = momentum < 0
    rsi_up = rsi >= 52
    rsi_dn = rsi <= 48

    # Day session (04:00-19:59 local): establish the selective MAIN trade
    # before considering fast sniper entries. The overlay worker may later add
    # one SNIPER while a MAIN is already open, but execution risk remains gated.
    day_main = 4 <= hour_local < 20
    if day_main and buy_score >= 6 and trend_up and mom_up:
        return Decision("MAIN", "BUY", min(10,buy_score+2), 1.0, 1.35, 2.0, "day_trend_structure")
    if day_main and sell_score >= 6 and trend_dn and mom_dn:
        return Decision("MAIN", "SELL", min(10,sell_score+2), 1.0, 1.35, 2.0, "day_trend_structure")

    # Fast sniper: momentum + RSI are the two primary triggers, but require
    # either trend alignment or a real structure break to avoid blind entries.
    if mom_up and rsi_up and (trend_up or break_up):
        strength = buy_score + int(trend_up) + int(break_up) + int(vol_ratio >= 1.05)
        if strength >= 7:
            night_boost = 1.20 if hour_local >= 20 and strength >= 8 and vol_ratio >= 1.10 else 1.0
            return Decision("SNIPER", "BUY", min(10,strength), night_boost, 0.85, 1.25, "momentum_rsi_aligned")
    if mom_dn and rsi_dn and (trend_dn or break_dn):
        strength = sell_score + int(trend_dn) + int(break_dn) + int(vol_ratio >= 1.05)
        if strength >= 7:
            night_boost = 1.20 if hour_local >= 20 and strength >= 8 and vol_ratio >= 1.10 else 1.0
            return Decision("SNIPER", "SELL", min(10,strength), night_boost, 0.85, 1.25, "momentum_rsi_aligned")

    # Outside the day window MAIN remains available when the sniper trigger did
    # not qualify; this preserves the previous night behavior.
    if buy_score >= 6 and trend_up and mom_up:
        return Decision("MAIN", "BUY", min(10,buy_score+2), 1.0, 1.35, 2.0, "trend_structure")
    if sell_score >= 6 and trend_dn and mom_dn:
        return Decision("MAIN", "SELL", min(10,sell_score+2), 1.0, 1.35, 2.0, "trend_structure")

    return Decision("WAIT", None, max(buy_score,sell_score), 0.0, 0.0, 0.0, "no_edge")

