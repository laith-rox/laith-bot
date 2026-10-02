"""Read-only gold intelligence for Laith Trading.

Combines validated XAU/USD structure with cached macro context.
Never sends broker orders and never changes MT5 state.
"""
from datetime import datetime, timezone
import math
import time
import requests

from engine import analyze, ema
from market import resample
from news import FEED, parse_calendar


class GoldIntelligence:
    def __init__(self, api_key, session=None):
        self.api_key = api_key
        self.session = session or requests.Session()
        self._macro_cache = {"at": 0.0, "value": None}
        self._news_cache = {"at": 0.0, "value": None}

    @staticmethod
    def _direction(value, threshold=0.05):
        if value is None:
            return "UNKNOWN"
        if value > threshold:
            return "UP"
        if value < -threshold:
            return "DOWN"
        return "FLAT"

    @staticmethod
    def _pct_change(rows, bars_back=4):
        if len(rows) <= bars_back:
            return None
        a = rows[-1-bars_back]["c"]
        b = rows[-1]["c"]
        if not a:
            return None
        return (b / a - 1.0) * 100.0

    @staticmethod
    def _pearson(xs, ys):
        if len(xs) != len(ys) or len(xs) < 8:
            return None
        mx = sum(xs) / len(xs)
        my = sum(ys) / len(ys)
        vx = sum((x-mx)**2 for x in xs)
        vy = sum((y-my)**2 for y in ys)
        if vx <= 0 or vy <= 0:
            return None
        cov = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
        return cov / math.sqrt(vx*vy)

    @staticmethod
    def _returns_by_time(rows):
        out = {}
        for prev, cur in zip(rows, rows[1:]):
            if prev["c"] > 0:
                out[cur["t"]] = cur["c"] / prev["c"] - 1.0
        return out

    def _td_series(self, symbol, outputsize=40):
        response = self.session.get(
            "https://api.twelvedata.com/time_series",
            params={
                "symbol": symbol,
                "interval": "15min",
                "outputsize": outputsize,
                "timezone": "UTC",
                "order": "ASC",
                "apikey": self.api_key,
                "format": "JSON",
            },
            timeout=(5, 15),
        )
        if response.status_code != 200:
            raise ValueError("macro_http_%s" % response.status_code)
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("status") == "error":
            raise ValueError("macro_provider_error")
        values = payload.get("values")
        if not isinstance(values, list) or len(values) < 8:
            raise ValueError("macro_insufficient_history")
        rows = []
        for row in values:
            dt = datetime.fromisoformat(str(row["datetime"]).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            rows.append({
                "t": int(dt.timestamp()),
                "o": float(row["open"]),
                "h": float(row["high"]),
                "l": float(row["low"]),
                "c": float(row["close"]),
            })
        rows.sort(key=lambda r: r["t"])
        return rows

    def signal(self, gold_bars, now):
        decision = analyze(gold_bars, now)
        m15 = resample(gold_bars, 15)
        recent = m15[-20:]
        closes = [b.close for b in m15]
        price = decision["price"]
        support = min(b.low for b in recent)
        resistance = max(b.high for b in recent)
        atr = float(decision["atr"])
        e20 = ema(closes, 20)[-1]
        e50 = ema(closes, 50)[-1]
        momentum = closes[-1] - closes[-4]
        score = max(int(decision.get("buy", 0)), int(decision.get("sell", 0)))
        bias = decision.get("side", "WAIT")
        entry_ready = bool(
            not decision.get("forced", True)
            and decision.get("context", {}).get("entry_allowed", False)
        )
        side = bias if entry_ready else "WAIT"
        if score >= 6:
            strength = "STRONG"
        elif score >= 5:
            strength = "MEDIUM"
        else:
            strength = "WEAK"
        if price <= support + 0.20 * atr:
            sr = "NEAR_SUPPORT"
        elif price >= resistance - 0.20 * atr:
            sr = "NEAR_RESISTANCE"
        else:
            sr = "IN_RANGE"
        return {
            "side": side,
            "bias": bias,
            "entryReady": entry_ready,
            "score": score,
            "strength": strength,
            "entry": price,
            "sl": decision.get("sl"),
            "tp1": decision.get("tp1"),
            "tp2": decision.get("tp2"),
            "rsi": round(float(decision.get("rsi", 50.0)), 2),
            "trend": "UP" if e20 > e50 else "DOWN" if e20 < e50 else "FLAT",
            "momentum": "UP" if momentum > 0 else "DOWN" if momentum < 0 else "FLAT",
            "support": support,
            "resistance": resistance,
            "sr": sr,
            "bar": decision.get("bar"),
            "reason": decision.get("reason"),
        }

    def macro(self, gold_bars):
        now_mono = time.monotonic()
        if self._macro_cache["value"] is not None and now_mono - self._macro_cache["at"] < 900:
            return self._macro_cache["value"]

        result = {
            "ok": True,
            "source": "Twelve Data",
            "oil": {"available": False},
            "usdProxy": {"available": False, "proxy": "inverse EUR/USD"},
        }

        try:
            oil = self._td_series("WTI/USD", 40)
            oil_change = self._pct_change(oil, 4)
            gold15 = resample(gold_bars, 15)[-40:]
            gold_rows = [{"t": int(b.start.timestamp()), "c": b.close} for b in gold15]
            gr = self._returns_by_time(gold_rows)
            OR = self._returns_by_time(oil)
            shared = sorted(set(gr) & set(OR))
            corr = self._pearson([gr[t] for t in shared], [OR[t] for t in shared])
            if corr is None:
                relation = "UNKNOWN"
            elif corr >= 0.35:
                relation = "DIRECT"
            elif corr <= -0.35:
                relation = "INVERSE"
            else:
                relation = "WEAK"
            result["oil"] = {
                "available": True,
                "symbol": "WTI/USD",
                "change1hPct": round(oil_change, 3) if oil_change is not None else None,
                "direction": self._direction(oil_change),
                "goldCorrelation15m": round(corr, 3) if corr is not None else None,
                "relation": relation,
            }
        except Exception as exc:
            result["oil"] = {"available": False, "error": str(exc)[:80]}

        try:
            eurusd = self._td_series("EUR/USD", 40)
            eur_change = self._pct_change(eurusd, 4)
            usd_change = -eur_change if eur_change is not None else None
            result["usdProxy"] = {
                "available": True,
                "proxy": "inverse EUR/USD",
                "change1hPct": round(usd_change, 3) if usd_change is not None else None,
                "direction": self._direction(usd_change),
            }
        except Exception as exc:
            result["usdProxy"] = {
                "available": False,
                "proxy": "inverse EUR/USD",
                "error": str(exc)[:80],
            }

        result["ok"] = bool(result["oil"].get("available") or result["usdProxy"].get("available"))
        self._macro_cache = {"at": now_mono, "value": result}
        return result

    def news(self, now):
        now_mono = time.monotonic()
        if self._news_cache["value"] is not None and now_mono - self._news_cache["at"] < 600:
            return self._news_cache["value"]
        result = {"ok": False, "blackout": False, "nextHighImpact": None}
        try:
            response = self.session.get(FEED, timeout=(5, 15))
            if response.status_code != 200:
                raise ValueError("calendar_http_%s" % response.status_code)
            events = parse_calendar(response.json(), now)
            current = now.timestamp()
            near = [e for e in events if -15*60 <= e["time"] - current <= 30*60]
            future = [e for e in events if e["time"] >= current]
            next_event = future[0] if future else None
            result = {
                "ok": True,
                "blackout": bool(near),
                "near": near[:3],
                "nextHighImpact": next_event,
            }
        except Exception as exc:
            result = {"ok": False, "blackout": False, "nextHighImpact": None, "error": str(exc)[:80]}
        self._news_cache = {"at": now_mono, "value": result}
        return result

    def snapshot(self, gold_bars, now):
        return {
            "analysis": self.signal(gold_bars, now),
            "macro": self.macro(gold_bars),
            "news": self.news(now),
            "execution": False,
        }
