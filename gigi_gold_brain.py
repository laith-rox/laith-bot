"""GIGI GOLD BRAIN v1 — read-only gold decision layer.

This module sits above the existing GoldIntelligence engine. It combines:
H4/H1/M15 structure, M5 timing, 7-condition scoring, correction detection,
macro alignment and high-impact news risk. It never sends broker orders.
"""
from engine import ema
from gold_intelligence import GoldIntelligence
from market import resample


class GigiGoldBrain(GoldIntelligence):
    @staticmethod
    def _trend(closes, fast=20, slow=50):
        if len(closes) < slow:
            return "UNKNOWN"
        a = ema(closes, fast)[-1]
        b = ema(closes, slow)[-1]
        return "UP" if a > b else "DOWN" if a < b else "FLAT"

    @staticmethod
    def _h4_closes(h1):
        buckets = {}
        for bar in h1:
            bucket = int(bar.start.timestamp()) // 14400 * 14400
            buckets.setdefault(bucket, []).append(bar)
        out = []
        for bucket, group in sorted(buckets.items()):
            group.sort(key=lambda b: b.start)
            expected = [bucket + i * 3600 for i in range(4)]
            if [int(b.start.timestamp()) for b in group] == expected:
                out.append(group[-1].close)
        return out

    @staticmethod
    def _conditions(names, values):
        items = [{"name": n, "passed": bool(v)} for n, v in zip(names, values)]
        return {
            "passed": sum(1 for item in items if item["passed"]),
            "total": len(items),
            "items": items,
        }

    @staticmethod
    def _macro_alignment(bias, macro):
        if bias not in ("BUY", "SELL"):
            return {"score": 0, "status": "NEUTRAL", "votes": []}

        votes = []
        usd = macro.get("usdProxy", {})
        if usd.get("available") and usd.get("direction") in ("UP", "DOWN"):
            votes.append({
                "factor": "USD",
                "supports": "BUY" if usd["direction"] == "DOWN" else "SELL",
            })

        oil = macro.get("oil", {})
        relation = oil.get("relation")
        oil_dir = oil.get("direction")
        if oil.get("available") and relation in ("DIRECT", "INVERSE") and oil_dir in ("UP", "DOWN"):
            if relation == "DIRECT":
                supports = "BUY" if oil_dir == "UP" else "SELL"
            else:
                supports = "SELL" if oil_dir == "UP" else "BUY"
            votes.append({"factor": "OIL", "supports": supports})

        score = sum(1 if vote["supports"] == bias else -1 for vote in votes)
        status = "SUPPORTS" if score > 0 else "OPPOSES" if score < 0 else "NEUTRAL"
        return {"score": score, "status": status, "votes": votes}

    def technical_brain(self, gold_bars, now):
        base = super().signal(gold_bars, now)
        m15 = resample(gold_bars, 15)
        h1 = resample(gold_bars, 60)

        c15 = [b.close for b in m15]
        c1h = [b.close for b in h1]
        c4h = self._h4_closes(h1)

        trend_m15 = self._trend(c15)
        trend_h1 = self._trend(c1h)
        trend_h4 = self._trend(c4h, 10, 20)

        m5 = gold_bars[-4:]
        m5_delta = m5[-1].close - m5[0].close if len(m5) == 4 else 0.0
        timing_m5 = "UP" if m5_delta > 0 else "DOWN" if m5_delta < 0 else "FLAT"

        bias = base.get("bias", "WAIT")
        expected = "UP" if bias == "BUY" else "DOWN"
        rsi = float(base.get("rsi", 50.0))

        location_ok = (
            base.get("sr") != "NEAR_RESISTANCE"
            if bias == "BUY"
            else base.get("sr") != "NEAR_SUPPORT"
        ) if bias in ("BUY", "SELL") else False

        condition_names = [
            "H4 trend",
            "H1 trend",
            "M15 trend",
            "M15 momentum",
            "RSI regime",
            "M5 timing",
            "location",
        ]
        condition_values = [
            trend_h4 == expected,
            trend_h1 == expected,
            trend_m15 == expected,
            base.get("momentum") == expected,
            (51 <= rsi <= 69) if bias == "BUY" else (31 <= rsi <= 49),
            timing_m5 == expected,
            location_ok,
        ] if bias in ("BUY", "SELL") else [False] * 7

        conditions = self._conditions(condition_names, condition_values)
        entry_ready = bool(base.get("entryReady") and conditions["passed"] >= 5)

        if conditions["passed"] >= 6:
            strength = "STRONG"
        elif conditions["passed"] >= 5:
            strength = "MEDIUM"
        else:
            strength = "WEAK"

        correction = "NONE"
        if trend_h1 == "UP" and timing_m5 == "DOWN":
            correction = "SELL_CORRECTION"
        elif trend_h1 == "DOWN" and timing_m5 == "UP":
            correction = "BUY_CORRECTION"

        atr = abs(float(base["entry"]) - float(base["sl"])) / 1.4 if base.get("sl") is not None else 0.0
        direction = 1 if bias == "BUY" else -1 if bias == "SELL" else 0
        tp3 = float(base["entry"]) + direction * 3.4 * atr if direction and atr else None
        zone_half = 0.12 * atr if atr else 0.0

        return {
            **base,
            "side": bias if entry_ready else "WAIT",
            "decision": "ENTER" if entry_ready else "WAIT",
            "entryReady": entry_ready,
            "strength": strength,
            "conditions": conditions,
            "trendH4": trend_h4,
            "trendH1": trend_h1,
            "trendM15": trend_m15,
            "timingM5": timing_m5,
            "correction": correction,
            "entryZoneLow": round(float(base["entry"]) - zone_half, 2),
            "entryZoneHigh": round(float(base["entry"]) + zone_half, 2),
            "invalidation": base.get("sl"),
            "tp3": round(tp3, 2) if tp3 is not None else None,
        }

    def snapshot(self, gold_bars, now):
        analysis = self.technical_brain(gold_bars, now)
        macro = super().macro(gold_bars)
        news = super().news(now)
        alignment = self._macro_alignment(analysis.get("bias"), macro)

        decision = analysis["decision"]
        reason = analysis.get("reason")
        if news.get("blackout"):
            decision = "WAIT_NEWS"
            reason = "high_impact_news_window"
        elif analysis.get("entryReady") and alignment["status"] == "OPPOSES":
            decision = "WAIT_MACRO"
            reason = "macro_opposes_technical_entry"

        gigi = {
            **analysis,
            "decision": decision,
            "macroAlignment": alignment,
            "newsRisk": "HIGH" if news.get("blackout") else "NORMAL",
            "reason": reason,
        }

        return {
            "analysis": analysis,
            "macro": macro,
            "news": news,
            "gigi": gigi,
            "execution": False,
        }
