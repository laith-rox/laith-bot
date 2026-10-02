"""GIGI GOLD BRAIN v2 — read-only gold decision layer.

Builds a market story before any trade decision:
- H4/H1/M15 trend + M5 timing
- every recent candle's body/wicks/range and sequence
- current trading day vs previous trading day
- prior-day high/low/open/close, today's open, sweeps and reclaims
- session context, support/resistance, momentum, RSI
- macro alignment and high-impact news risk

It never sends broker orders.
"""
from datetime import time as dtime
from zoneinfo import ZoneInfo

from engine import ema
from gold_intelligence import GoldIntelligence
from market import resample


NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


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
    def _trading_day(dt):
        """Gold trading day rolls at 17:00 New York."""
        local = dt.astimezone(NY)
        day = local.date()
        if local.time() >= dtime(17, 0):
            return day.fromordinal(day.toordinal() + 1)
        return day

    @classmethod
    def _day_groups(cls, bars):
        groups = {}
        for bar in bars:
            groups.setdefault(cls._trading_day(bar.start), []).append(bar)
        for group in groups.values():
            group.sort(key=lambda b: b.start)
        return groups

    @staticmethod
    def _ohlc(group):
        if not group:
            return None
        return {
            "open": group[0].open,
            "high": max(b.high for b in group),
            "low": min(b.low for b in group),
            "close": group[-1].close,
        }

    @staticmethod
    def _candle_features(bar, avg_range):
        rng = max(bar.high - bar.low, 1e-9)
        body = abs(bar.close - bar.open)
        upper = bar.high - max(bar.open, bar.close)
        lower = min(bar.open, bar.close) - bar.low
        direction = "BULL" if bar.close > bar.open else "BEAR" if bar.close < bar.open else "DOJI"
        body_ratio = body / rng
        event = "NORMAL"
        if body_ratio <= 0.18:
            event = "DOJI"
        elif lower / rng >= 0.55 and body_ratio <= 0.40:
            event = "LOWER_REJECTION"
        elif upper / rng >= 0.55 and body_ratio <= 0.40:
            event = "UPPER_REJECTION"
        elif avg_range and rng >= 1.6 * avg_range and body_ratio >= 0.65:
            event = "BULL_DISPLACEMENT" if direction == "BULL" else "BEAR_DISPLACEMENT"
        return {
            "direction": direction,
            "event": event,
            "bodyRatio": round(body_ratio, 3),
            "upperWickRatio": round(upper / rng, 3),
            "lowerWickRatio": round(lower / rng, 3),
            "range": round(rng, 3),
            "close": bar.close,
        }

    @classmethod
    def _candle_story(cls, bars, lookback=12):
        recent = bars[-lookback:]
        if not recent:
            return {"sequence": [], "bullCount": 0, "bearCount": 0, "streak": 0}
        prior_ranges = [b.high - b.low for b in bars[-30:-1] if b.high > b.low]
        avg_range = sum(prior_ranges) / len(prior_ranges) if prior_ranges else 0.0
        sequence = [cls._candle_features(b, avg_range) for b in recent]

        bull = sum(1 for item in sequence if item["direction"] == "BULL")
        bear = sum(1 for item in sequence if item["direction"] == "BEAR")
        last_dir = sequence[-1]["direction"]
        streak = 0
        for item in reversed(sequence):
            if item["direction"] != last_dir or last_dir == "DOJI":
                break
            streak += 1

        last = sequence[-1]
        prev = sequence[-2] if len(sequence) >= 2 else None
        pattern = last["event"]
        if prev:
            a, b = recent[-2], recent[-1]
            if b.close > b.open and a.close < a.open and b.open <= a.close and b.close >= a.open:
                pattern = "BULL_ENGULFING"
            elif b.close < b.open and a.close > a.open and b.open >= a.close and b.close <= a.open:
                pattern = "BEAR_ENGULFING"

        return {
            "sequence": sequence,
            "bullCount": bull,
            "bearCount": bear,
            "lastDirection": last_dir,
            "streak": streak,
            "lastPattern": pattern,
            "avgRange": round(avg_range, 3),
        }

    @classmethod
    def _daily_story(cls, bars, now):
        groups = cls._day_groups(bars)
        today_key = cls._trading_day(now)
        keys = sorted(groups)
        today = groups.get(today_key, [])
        prior_keys = [k for k in keys if k < today_key]
        previous = groups[prior_keys[-1]] if prior_keys else []

        td = cls._ohlc(today)
        pd = cls._ohlc(previous)
        if not td or not pd:
            return {
                "available": False,
                "tradingDay": str(today_key),
                "reason": "insufficient_day_history",
            }

        price = today[-1].close
        pd_range = max(pd["high"] - pd["low"], 1e-9)
        position = (price - pd["low"]) / pd_range

        swept_high = td["high"] > pd["high"]
        swept_low = td["low"] < pd["low"]
        reclaimed_below_high = swept_high and price < pd["high"]
        reclaimed_above_low = swept_low and price > pd["low"]

        if price > pd["high"]:
            location = "ABOVE_PREVIOUS_HIGH"
        elif price < pd["low"]:
            location = "BELOW_PREVIOUS_LOW"
        elif position >= 0.67:
            location = "UPPER_THIRD"
        elif position <= 0.33:
            location = "LOWER_THIRD"
        else:
            location = "MID_RANGE"

        event = "INSIDE_PREVIOUS_RANGE"
        directional_hint = "NEUTRAL"
        if swept_high and reclaimed_below_high:
            event, directional_hint = "HIGH_SWEEP_REJECTION", "SELL"
        elif swept_low and reclaimed_above_low:
            event, directional_hint = "LOW_SWEEP_REJECTION", "BUY"
        elif price > pd["high"]:
            event, directional_hint = "HIGH_BREAK_ACCEPTANCE", "BUY"
        elif price < pd["low"]:
            event, directional_hint = "LOW_BREAK_ACCEPTANCE", "SELL"
        elif price > td["open"] and pd["close"] >= pd["open"]:
            directional_hint = "BUY"
        elif price < td["open"] and pd["close"] <= pd["open"]:
            directional_hint = "SELL"

        return {
            "available": True,
            "tradingDay": str(today_key),
            "today": {k: round(v, 2) for k, v in td.items()},
            "previous": {k: round(v, 2) for k, v in pd.items()},
            "previousRangePosition": round(position, 3),
            "location": location,
            "event": event,
            "directionalHint": directional_hint,
            "sweptPreviousHigh": swept_high,
            "sweptPreviousLow": swept_low,
            "aboveTodayOpen": price > td["open"],
            "distanceFromTodayOpen": round(price - td["open"], 2),
        }

    @classmethod
    def _weekly_story(cls, bars, now):
        """Current week versus the most recent completed trading week."""
        groups = {}
        for bar in bars:
            d = cls._trading_day(bar.start)
            iso = d.isocalendar()
            key = (iso.year, iso.week)
            groups.setdefault(key, []).append(bar)
        for group in groups.values():
            group.sort(key=lambda b: b.start)

        current_day = cls._trading_day(now)
        iso = current_day.isocalendar()
        current_key = (iso.year, iso.week)
        current = groups.get(current_key, [])
        prior_keys = sorted(k for k in groups if k < current_key)
        previous = groups[prior_keys[-1]] if prior_keys else []
        cw, pw = cls._ohlc(current), cls._ohlc(previous)
        if not cw or not pw:
            return {"available": False}

        price = current[-1].close
        if price > pw["high"]:
            event = "ABOVE_PREVIOUS_WEEK_HIGH"
            hint = "BUY"
        elif price < pw["low"]:
            event = "BELOW_PREVIOUS_WEEK_LOW"
            hint = "SELL"
        elif cw["high"] > pw["high"] and price < pw["high"]:
            event = "WEEK_HIGH_SWEEP_REJECTION"
            hint = "SELL"
        elif cw["low"] < pw["low"] and price > pw["low"]:
            event = "WEEK_LOW_SWEEP_REJECTION"
            hint = "BUY"
        else:
            event = "INSIDE_PREVIOUS_WEEK"
            hint = "NEUTRAL"

        return {
            "available": True,
            "current": {k: round(v, 2) for k, v in cw.items()},
            "previous": {k: round(v, 2) for k, v in pw.items()},
            "event": event,
            "directionalHint": hint,
        }

    @staticmethod
    def _market_regime(m15, h1):
        if len(m15) < 30 or len(h1) < 30:
            return {"type": "UNKNOWN", "compression": None}
        c15 = [b.close for b in m15]
        c1h = [b.close for b in h1]
        e20_15 = ema(c15, 20)
        e20_h1 = ema(c1h, 20)
        slope15 = e20_15[-1] - e20_15[-5]
        slope1h = e20_h1[-1] - e20_h1[-4]
        ranges = [b.high - b.low for b in m15[-20:]]
        recent = sum(ranges[-5:]) / 5
        baseline = sum(ranges) / len(ranges)
        compression = recent / baseline if baseline else 1.0

        same = (slope15 > 0 and slope1h > 0) or (slope15 < 0 and slope1h < 0)
        if same and abs(slope1h) > 0:
            regime = "TREND"
        elif compression < 0.70:
            regime = "COMPRESSION"
        else:
            regime = "RANGE"
        return {
            "type": regime,
            "direction": "UP" if slope1h > 0 else "DOWN" if slope1h < 0 else "FLAT",
            "compression": round(compression, 3),
        }

    @staticmethod
    def _liquidity_map(price, daily, weekly, sessions):
        levels = []
        if daily.get("available"):
            pd = daily["previous"]
            td = daily["today"]
            levels += [
                ("PDH", pd["high"]), ("PDL", pd["low"]),
                ("TODAY_HIGH", td["high"]), ("TODAY_LOW", td["low"]),
                ("TODAY_OPEN", td["open"]),
            ]
        if weekly.get("available"):
            pw = weekly["previous"]
            levels += [("PWH", pw["high"]), ("PWL", pw["low"])]
        for name, row in sessions.get("ranges", {}).items():
            levels += [(name + "_HIGH", row["high"]), (name + "_LOW", row["low"])]

        # Deduplicate near-identical levels while retaining useful labels.
        merged = []
        for label, level in sorted(levels, key=lambda x: x[1]):
            if merged and abs(level - merged[-1]["price"]) < 0.05:
                merged[-1]["labels"].append(label)
            else:
                merged.append({"price": float(level), "labels": [label]})

        above = [x for x in merged if x["price"] > price]
        below = [x for x in merged if x["price"] < price]
        nearest_above = min(above, key=lambda x: x["price"] - price) if above else None
        nearest_below = min(below, key=lambda x: price - x["price"]) if below else None
        return {
            "nearestAbove": nearest_above,
            "nearestBelow": nearest_below,
            "all": merged[-20:],
        }

    @staticmethod
    def _session_story(bars, now):
        hour = now.astimezone(UTC).hour
        if 0 <= hour < 7:
            active = "ASIA"
        elif 7 <= hour < 13:
            active = "LONDON"
        elif 13 <= hour < 21:
            active = "NEW_YORK"
        else:
            active = "ROLLOVER"

        today = now.astimezone(UTC).date()
        same_date = [b for b in bars if b.start.astimezone(UTC).date() == today]
        ranges = {}
        windows = {"ASIA": (0, 7), "LONDON": (7, 13), "NEW_YORK": (13, 21)}
        for name, (start_h, end_h) in windows.items():
            group = [b for b in same_date if start_h <= b.start.astimezone(UTC).hour < end_h]
            if group:
                ranges[name] = {
                    "high": round(max(b.high for b in group), 2),
                    "low": round(min(b.low for b in group), 2),
                    "open": round(group[0].open, 2),
                    "close": round(group[-1].close, 2),
                }
        return {"active": active, "ranges": ranges}

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

    @staticmethod
    def _story_alignment(bias, daily, candle_story):
        if bias not in ("BUY", "SELL"):
            return "NEUTRAL"
        votes = 0
        hint = daily.get("directionalHint")
        if hint in ("BUY", "SELL"):
            votes += 1 if hint == bias else -1

        last = candle_story.get("lastPattern", "")
        if last in ("BULL_ENGULFING", "BULL_DISPLACEMENT", "LOWER_REJECTION"):
            votes += 1 if bias == "BUY" else -1
        elif last in ("BEAR_ENGULFING", "BEAR_DISPLACEMENT", "UPPER_REJECTION"):
            votes += 1 if bias == "SELL" else -1

        return "SUPPORTS" if votes > 0 else "OPPOSES" if votes < 0 else "NEUTRAL"

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

        candle_story = self._candle_story(gold_bars)
        daily_story = self._daily_story(gold_bars, now)
        weekly_story = self._weekly_story(gold_bars, now)
        session_story = self._session_story(gold_bars, now)
        regime = self._market_regime(m15, h1)
        liquidity = self._liquidity_map(
            float(base["entry"]), daily_story, weekly_story, session_story
        )

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
        story_alignment = self._story_alignment(bias, daily_story, candle_story)

        # Keep the 7-condition core, but require the market story not to directly
        # contradict a strict entry. A neutral story does not block a trade.
        entry_ready = bool(
            base.get("entryReady")
            and conditions["passed"] >= 5
            and story_alignment != "OPPOSES"
        )

        if conditions["passed"] >= 6 and story_alignment == "SUPPORTS":
            strength = "STRONG"
        elif conditions["passed"] >= 5 and story_alignment != "OPPOSES":
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
            "candleStory": candle_story,
            "dailyStory": daily_story,
            "weeklyStory": weekly_story,
            "sessionStory": session_story,
            "marketRegime": regime,
            "liquidityMap": liquidity,
            "storyAlignment": story_alignment,
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
        elif analysis.get("storyAlignment") == "OPPOSES":
            decision = "WAIT_STORY"
            reason = "candle_and_day_story_opposes_entry"

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
