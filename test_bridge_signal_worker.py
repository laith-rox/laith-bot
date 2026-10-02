import unittest
import datetime as dt
from unittest.mock import patch
import bridge_signal_worker as worker

from bridge_signal_worker import compute_signal, normalize_rows


def make_values(direction="up"):
    rows = []
    price = 4300.0
    for i in range(42):
        step = 1.2 if direction == "up" else -1.2
        open_ = price
        close = price + step
        high = max(open_, close) + 0.35
        low = min(open_, close) - 0.35
        rows.append({
            "datetime": f"2026-09-21 {i//12:02d}:{(i%12)*5:02d}:00",
            "open": f"{open_:.2f}",
            "high": f"{high:.2f}",
            "low": f"{low:.2f}",
            "close": f"{close:.2f}",
        })
        price = close
    # Twelve Data returns newest first. Add one active candle that must be ignored.
    active = dict(rows[-1])
    active["datetime"] = "2026-09-21 23:59:00"
    return [active] + list(reversed(rows))


def with_latest(values, *, open_, high, low, close):
    values = [dict(row) for row in values]
    # values[0] is active; values[1] is the latest closed candle.
    values[1].update(open=f"{open_:.2f}", high=f"{high:.2f}",
                     low=f"{low:.2f}", close=f"{close:.2f}")
    return values


class BridgeSignalWorkerTests(unittest.TestCase):
    def test_normalize_drops_active_candle(self):
        values = make_values("up")
        rows = normalize_rows(values)
        self.assertEqual(len(rows), len(values) - 1)
        self.assertNotEqual(rows[-1]["datetime"], "2026-09-21 23:59:00")

    def test_bar_seconds_do_not_make_duplicate_signal_keys(self):
        values=make_values("up")
        first=compute_signal(values)
        values[1]["datetime"]=values[1]["datetime"][:-2]+"01"
        second=compute_signal(values)
        self.assertEqual(first["bar"],second["bar"])

    def test_strong_uptrend_can_use_local_medium_invalidation(self):
        signal = compute_signal(make_values("up"))
        self.assertGreaterEqual(signal["score"], 6)
        self.assertEqual(signal["side"], "BUY")
        self.assertEqual(signal["reason"], "technical_medium_local_invalidation")
        self.assertLessEqual(signal["risk_distance"], 3.20)

    def test_strong_downtrend_can_use_local_medium_invalidation(self):
        signal = compute_signal(make_values("down"))
        self.assertGreaterEqual(signal["score"], 6)
        self.assertEqual(signal["side"], "SELL")
        self.assertEqual(signal["reason"], "technical_medium_local_invalidation")
        self.assertLessEqual(signal["risk_distance"], 3.20)

    def test_first_break_above_resistance_is_not_chased(self):
        values = make_values("up")
        base = float(values[8]["close"])
        # Six closed candles form a horizontal resistance; only the latest
        # candle pokes above it, so there is no one-bar hold confirmation yet.
        for i in range(2, 9):
            values[i].update(open=f"{base:.2f}", high=f"{base+0.30:.2f}",
                             low=f"{base-0.30:.2f}", close=f"{base:.2f}")
        values = with_latest(values, open_=base, high=base+1.35,
                             low=base-0.10, close=base+1.05)
        signal = compute_signal(values)
        self.assertIsNone(signal["side"])
        self.assertEqual(signal["reason"], "resistance_not_confirmed")

    def test_sell_pullback_inside_larger_uptrend_is_blocked(self):
        values = make_values("up")
        previous = float(values[2]["close"])
        values = with_latest(values, open_=previous+0.25, high=previous+0.35,
                             low=previous-2.20, close=previous-2.00)
        signal = compute_signal(values)
        if signal["sell_score"] >= 5:
            self.assertIsNone(signal["side"])
            self.assertEqual(signal["reason"], "sell_is_correction_in_uptrend")



class StopWorker(BaseException):
    pass


class PublishLimitTests(unittest.TestCase):
    def run_worker(self, cap, health, iterations=14):
        health = {"mode": "DEMO", **health}
        signals = [
            {"bar": str(i), "side": "BUY", "score": 6,
             "reference_close": 4300.0, "risk_distance": 1.2}
            for i in range(iterations)
        ]
        with patch.multiple(worker, BRIDGE_URL="https://example.invalid",
                            BRIDGE_PUBLISH_TOKEN="test-only",
                            MAX_PUBLISH_PER_HOUR=cap,
                            ALLOW_STALE_MT5_STATE=False), \
             patch.object(worker, "bridge_health", return_value=health), \
             patch.object(worker, "fetch_multitimeframe_values", return_value={"5m":[],"15m":[],"h4":[]}), \
             patch.object(worker, "validate_market_feed_freshness", return_value={"5m":0,"15m":0,"h4":0}), \
             patch.object(worker, "normalize_rows", return_value=[]), \
             patch.object(worker, "analyze_structure", return_value={"side":"BUY"}), \
             patch.object(worker, "apply_main_structure", side_effect=lambda s,m:s), \
             patch.object(worker, "same_entry_copies", return_value=1), \
             patch.object(worker, "compute_signal", side_effect=signals), \
             patch.object(worker, "publish_signal",
                          return_value=(201, {"ok": True}, "test")) as publish, \
             patch.object(worker.time, "time", return_value=1000.0), \
             patch.object(worker.time, "sleep",
                          side_effect=[None] * (iterations - 1) + [StopWorker()]), \
             patch("builtins.print"):
            with self.assertRaises(StopWorker):
                worker.run_forever()
            return publish.call_count

    def test_zero_allows_more_than_twelve_signals_without_hourly_wait(self):
        self.assertEqual(self.run_worker(0, {
            "enabled": True, "client_state_fresh": True,
            "position_open": False, "pending": 0}), 14)

    def test_positive_cap_still_limits_publishing(self):
        self.assertEqual(self.run_worker(2, {
            "enabled": True, "client_state_fresh": True,
            "position_open": False, "pending": 0}), 2)

    def test_unlimited_does_not_bypass_execution_state_checks(self):
        for changes in ({"enabled": False}, {"client_state_fresh": False},
                        {"pending": 4}):
            health = {"enabled": True, "client_state_fresh": True,
                      "position_open": False, "pending": 0}
            health.update(changes)
            with self.subTest(changes=changes):
                self.assertEqual(self.run_worker(0, health), 0)

    def test_negative_cap_is_configuration_error(self):
        with patch.object(worker, "MAX_PUBLISH_PER_HOUR", -1):
            with self.assertRaisesRegex(RuntimeError, "invalid_max_publish_per_hour"):
                worker.validate_config()


class TechnicalRecoveredMediumTests(unittest.TestCase):
    def test_strong_erased_buy_can_recover_with_technical_consensus(self):
        signal={"side":None,"mode":"MAIN","score":6,"confidence":7,"reason":"resistance_not_confirmed",
                "target_r":2.0,"local_buy_risk":1.2,
                "technical":{"bull_score":5,"bear_score":1}}
        mtf={"side":None,"reason":"mtf_wait","h4_bias":"DOWN",
             "m5_confirm_buy":True,"m5_confirm_sell":False}
        out=worker.apply_main_structure(signal,mtf)
        self.assertEqual(out["side"],"BUY")
        self.assertEqual(out["mode"],"SNIPER")
        self.assertEqual(out["reason"],"technical_medium_recovered")
        self.assertLessEqual(out["risk_distance"],1.60)

    def test_recovered_medium_never_widens_past_cap(self):
        signal={"side":None,"mode":"MAIN","score":7,"confidence":8,"reason":"x",
                "local_buy_risk":2.2,"technical":{"bull_score":6,"bear_score":1}}
        mtf={"side":None,"reason":"mtf_wait","h4_bias":"DOWN",
             "m5_confirm_buy":True,"m5_confirm_sell":False}
        out=worker.apply_main_structure(signal,mtf)
        self.assertIsNone(out["side"])


class MediumContinuationTests(unittest.TestCase):
    def test_clean_buy_is_not_erased_by_strict_mtf_wait(self):
        signal={"side":"BUY","mode":"MAIN","score":6,"confidence":7,"reason":"x"}
        mtf={"side":None,"reason":"mtf_wait","h4_bias":"UP",
             "m5_confirm_buy":True,"m5_confirm_sell":False}
        out=worker.apply_main_structure(signal,mtf)
        self.assertEqual(out["side"],"BUY")
        self.assertEqual(out["mode"],"SNIPER")
        self.assertEqual(out["reason"],"mtf_medium_continuation")

    def test_strong_countertrend_buy_becomes_medium_sniper(self):
        signal={"side":"BUY","mode":"MAIN","score":6,"confidence":7,"reason":"x","target_r":2.0}
        mtf={"side":None,"reason":"mtf_wait","h4_bias":"DOWN",
             "m5_confirm_buy":True,"m5_confirm_sell":False}
        out=worker.apply_main_structure(signal,mtf)
        self.assertEqual(out["side"],"BUY")
        self.assertEqual(out["mode"],"SNIPER")
        self.assertEqual(out["reason"],"mtf_countertrend_medium")
        self.assertEqual(out["target_r"],1.0)


class M15ContinuationStopTests(unittest.TestCase):
    def setUp(self):
        self.signal={"side":None,"reason":"structure_stop_exceeds_risk_cap",
                     "reference_close":4119.0,"buy_score":1,"sell_score":6,
                     "checks":{"SELL":[True,True,True,True,True,True,False]},
                     "mtf":{"h4_bias":"DOWN","m5_confirm_sell":True,
                            "m15_last_open":4124.0,"m15_last_close":4119.0,
                            "m15_prev_close":4123.0,"m15_last_high":4126.0,
                            "m15_prev_high":4127.0,"m15_atr":4.0,
                            "break_down":True}}
        self.health={"client_state_fresh":True,"effective_risk_budget_usd":"3.00",
                     "strong_risk_budget_usd":"15.00","total_position_risk_usd":"0.00"}

    def test_strong_breakout_uses_m15_high_and_budget(self):
        out=worker.recover_m15_continuation(self.signal,self.health)
        self.assertEqual(out["side"],"SELL")
        self.assertEqual(out["mode"],"MAIN")
        self.assertAlmostEqual(out["risk_distance"],8.4)
        self.assertEqual(out["analysis"]["invalidation"],"m15_candle_extreme")

    def test_medium_entry_needs_regular_budget(self):
        s={**self.signal,"sell_score":5,
           "checks":{"SELL":[True,True,False,True,True,True,False]}}
        self.assertIsNone(worker.recover_m15_continuation(s,self.health)["side"])
        s["mtf"]={**s["mtf"],"m15_last_high":4120.0,"m15_prev_high":4121.0}
        self.assertEqual(worker.recover_m15_continuation(s,self.health)["side"],"SELL")

    def test_no_countertrend_or_unconfirmed_m5_entry(self):
        for change in ({"h4_bias":"UP"},{"m5_confirm_sell":False},
                       {"m15_last_close":4125.0}):
            s={**self.signal,"mtf":{**self.signal["mtf"],**change}}
            with self.subTest(change=change):
                self.assertIsNone(worker.recover_m15_continuation(s,self.health)["side"])

    def test_no_entry_without_fresh_state(self):
        self.assertIsNone(worker.recover_m15_continuation(
            self.signal,{**self.health,"client_state_fresh":False})["side"])


class StrongStructuralEntryTests(unittest.TestCase):
    def setUp(self):
        self.signal = {"side": None, "reason": "structure_stop_exceeds_risk_cap",
                       "buy_score": 2, "sell_score": 7, "local_sell_risk": 4.24,
                       "mtf": {"h4_bias": "DOWN", "m5_confirm_sell": True},
                       "technical": {"bear_score": 5, "bull_score": 2}}
        self.health = {"client_state_fresh": True, "effective_risk_budget_usd": "4.72",
                       "total_position_risk_usd": "0.00"}

    def test_strong_aligned_sell_uses_candle_invalidation_within_budget(self):
        result = worker.recover_strong_structural_entry(self.signal, self.health)
        self.assertEqual(result["side"], "SELL")
        self.assertEqual(result["risk_distance"], 4.24)
        self.assertEqual(result["target_r"], 1.0)

    def test_wide_stop_cannot_be_clipped_to_fit_budget(self):
        result = worker.recover_strong_structural_entry(
            {**self.signal, "local_sell_risk": 8.71}, self.health)
        self.assertIsNone(result["side"])
        self.assertEqual(result["reason"], "strong_signal_stop_exceeds_budget")

    def test_strong_setup_can_use_fifteen_dollar_cap_reported_by_ea(self):
        result = worker.recover_strong_structural_entry(
            {**self.signal, "local_sell_risk": 12.0},
            {**self.health, "strong_risk_budget_usd": "15.00"})
        self.assertEqual(result["side"], "SELL")
        self.assertEqual(result["risk_distance"], 12.0)
        result = worker.recover_strong_structural_entry(
            {**self.signal, "local_sell_risk": 15.1},
            {**self.health, "strong_risk_budget_usd": "15.00"})
        self.assertIsNone(result["side"])

    def test_countertrend_requires_confirmed_breakout(self):
        result = worker.recover_strong_structural_entry(
            {**self.signal, "buy_score": 7, "sell_score": 2, "local_buy_risk": 3.1,
             "mtf": {"h4_bias": "DOWN", "m5_confirm_buy": True, "break_up": False},
             "technical": {"bear_score": 1, "bull_score": 5}}, self.health)
        self.assertIsNone(result["side"])

    def test_unconfirmed_resistance_is_not_overridden(self):
        result = worker.recover_strong_structural_entry(
            {**self.signal, "reason": "resistance_not_confirmed"}, self.health)
        self.assertIsNone(result["side"])


class MultiPositionDecisionTests(unittest.TestCase):
    def test_open_position_does_not_block_when_pending_capacity_exists(self):
        health={"mode":"DEMO","enabled":True,"client_state_fresh":True,
                "position_open":True,"pending":0}
        self.assertIsNone(worker.execution_block_reason(health))

    def test_pending_capacity_still_blocks(self):
        health={"mode":"DEMO","enabled":True,"client_state_fresh":True,
                "position_open":True,"pending":4}
        self.assertEqual(worker.execution_block_reason(health),"pending_command_limit")

    def test_same_entry_copies_use_remaining_ea_budget(self):
        signal={"risk_distance":1.0}
        health={"effective_risk_budget_usd":"6.00","total_position_risk_usd":"1.00"}
        self.assertEqual(worker.same_entry_copies(signal,health),1)

    def test_strong_budget_only_applies_to_verified_strong_checks(self):
        health={"effective_risk_budget_usd":"4.72","strong_risk_budget_usd":"15.00",
                "total_position_risk_usd":"0.00"}
        strong={"side":"SELL","checks":{"SELL":[True]*6+[False]},"risk_distance":12.0}
        weak={"side":"SELL","checks":{"SELL":[True]*5+[False]*2},"risk_distance":12.0}
        self.assertEqual(worker.same_entry_copies(strong,health),1)
        self.assertEqual(worker.same_entry_copies(weak,health),0)


class LegacyCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.health = {"mode": "DEMO", "enabled": True,
                       "client_state_fresh": False, "client_last_seen_age": None,
                       "client_poll_fresh": True, "position_open": False, "pending": 0}

    def test_legacy_polling_requires_explicit_compatibility(self):
        with patch.object(worker, "ALLOW_STALE_MT5_STATE", False):
            self.assertEqual(worker.execution_block_reason(self.health), "mt5_state_stale")
        with patch.object(worker, "ALLOW_STALE_MT5_STATE", True):
            self.assertIsNone(worker.execution_block_reason(self.health))

    def test_compatibility_never_accepts_disconnected_or_stale_reporting_clients(self):
        with patch.object(worker, "ALLOW_STALE_MT5_STATE", True):
            for changes, reason in [
                ({"client_poll_fresh": False}, "mt5_disconnected"),
                ({"client_last_seen_age": 11}, "mt5_state_stale"),
                ({"mode": "LIVE"}, "bridge_not_demo"),
                ({"enabled": False}, "bridge_disabled"),
                ({"pending": 4}, "pending_command_limit"),
            ]:
                with self.subTest(changes=changes):
                    self.assertEqual(worker.execution_block_reason({**self.health, **changes}), reason)



class MarketFreshnessTests(unittest.TestCase):
    def _feed(self, minutes, active_time, count=40):
        rows=[]
        start=active_time-dt.timedelta(minutes=minutes*(count-1))
        for i in range(count):
            t=start+dt.timedelta(minutes=minutes*i)
            rows.append({"datetime":t.strftime("%Y-%m-%d %H:%M:%S"),
                         "open":"4100.0","high":"4101.0","low":"4099.0","close":"4100.5"})
        return rows

    def test_fresh_multitimeframe_feed_is_accepted(self):
        now=dt.datetime(2026,10,2,18,50,tzinfo=dt.timezone.utc)
        feeds={
            "5m":self._feed(5, now.replace(tzinfo=None)),
            "15m":self._feed(15, now.replace(minute=45,tzinfo=None)),
            "h4":self._feed(240, now.replace(hour=16,minute=0,tzinfo=None)),
        }
        ages=worker.validate_market_feed_freshness(feeds, now.timestamp())
        self.assertLessEqual(ages["5m"], 15*60)
        self.assertLessEqual(ages["15m"], 40*60)
        self.assertLessEqual(ages["h4"], 9*60*60)

    def test_day_old_m5_feed_is_rejected(self):
        now=dt.datetime(2026,10,2,18,50,tzinfo=dt.timezone.utc)
        feeds={
            "5m":self._feed(5, dt.datetime(2026,10,1,18,50)),
            "15m":self._feed(15, now.replace(minute=45,tzinfo=None)),
            "h4":self._feed(240, now.replace(hour=16,minute=0,tzinfo=None)),
        }
        with self.assertRaisesRegex(RuntimeError, "stale_market_data:5m"):
            worker.validate_market_feed_freshness(feeds, now.timestamp())


class RelaxedOfficialContinuationTests(unittest.TestCase):
    def test_aligned_five_of_seven_can_be_main_without_strict_breakout(self):
        signal={"side":None,"reason":"structure_stop_exceeds_risk_cap",
                "reference_close":4119.0,"buy_score":1,"sell_score":5,
                "checks":{"SELL":[True,True,False,True,True,True,False]},
                "mtf":{"h4_bias":"DOWN","m5_confirm_sell":True,
                       "m15_last_open":4122.0,"m15_last_close":4119.0,
                       "m15_prev_close":4121.0,"m15_last_high":4120.0,
                       "m15_prev_high":4121.0,"m15_atr":4.0,
                       "break_down":False}}
        health={"client_state_fresh":True,"effective_risk_budget_usd":"3.00",
                "strong_risk_budget_usd":"15.00","total_position_risk_usd":"0.00"}
        out=worker.recover_m15_continuation(signal,health)
        self.assertEqual(out["side"],"SELL")
        self.assertEqual(out["mode"],"MAIN")
        self.assertEqual(out["reason"],"m15_aligned_official_continuation")
        self.assertLessEqual(out["risk_distance"],3.0)

    def test_five_of_seven_without_h4_alignment_stays_blocked(self):
        signal={"side":None,"reason":"structure_stop_exceeds_risk_cap",
                "reference_close":4119.0,"buy_score":1,"sell_score":5,
                "checks":{"SELL":[True,True,False,True,True,True,False]},
                "mtf":{"h4_bias":"UP","m5_confirm_sell":True,
                       "m15_last_open":4122.0,"m15_last_close":4119.0,
                       "m15_prev_close":4121.0,"m15_last_high":4120.0,
                       "m15_prev_high":4121.0,"m15_atr":4.0,
                       "break_down":False}}
        health={"client_state_fresh":True,"effective_risk_budget_usd":"3.00",
                "strong_risk_budget_usd":"15.00","total_position_risk_usd":"0.00"}
        self.assertIsNone(worker.recover_m15_continuation(signal,health)["side"])


class SniperRiskLadderTests(unittest.TestCase):
    def _signal(self, strength, risk=1.0):
        checks=[True]*strength+[False]*(7-strength)
        return {"side":"BUY","mode":"NIGHT_SNIPER","score":strength,
                "checks":{"BUY":checks},"risk_distance":risk}

    def test_sniper_budget_ladder(self):
        expected={3:2.0,4:2.0,5:3.0,6:5.0,7:7.0}
        for strength,budget in expected.items():
            with self.subTest(strength=strength):
                self.assertEqual(worker.sniper_budget_usd(self._signal(strength)),budget)

    def test_worker_caps_strong_sniper_to_tier(self):
        health={"effective_risk_budget_usd":"3.00","strong_risk_budget_usd":"15.00",
                "total_position_risk_usd":"0.00"}
        self.assertEqual(worker.same_entry_copies(self._signal(6,5.0),health),1)
        self.assertEqual(worker.same_entry_copies(self._signal(6,5.1),health),0)
        self.assertEqual(worker.same_entry_copies(self._signal(7,7.0),health),1)
        self.assertEqual(worker.same_entry_copies(self._signal(7,7.1),health),0)


class SniperChaseTests(unittest.TestCase):
    def _signal(self, strength=5, side="BUY", bar="2026-10-02 19:35:00", held=False):
        checks=[True]*strength+[False]*(7-strength)
        return {"side":side,"mode":"NIGHT_SNIPER","score":strength,"bar":bar,
                "checks":{side:checks},"held_breakout":held,"mtf":{}}

    def test_same_direction_next_bar_needs_improvement_or_break(self):
        s=self._signal(5,bar="2026-10-02 19:40:00")
        self.assertEqual(worker.sniper_chase_block_reason(
            s,"BUY",5,"2026-10-02 19:35:00"),"same_direction_sniper_chase")
        self.assertIsNone(worker.sniper_chase_block_reason(
            self._signal(6,bar="2026-10-02 19:40:00"),"BUY",5,"2026-10-02 19:35:00"))
        self.assertIsNone(worker.sniper_chase_block_reason(
            self._signal(5,bar="2026-10-02 19:40:00",held=True),"BUY",5,"2026-10-02 19:35:00"))

    def test_opposite_side_is_not_chase_blocked(self):
        self.assertIsNone(worker.sniper_chase_block_reason(
            self._signal(5,side="SELL",bar="2026-10-02 19:40:00"),
            "BUY",5,"2026-10-02 19:35:00"))


class SniperM15FilterTests(unittest.TestCase):
    def _mtf(self, direction):
        if direction=="BUY":
            o,c,p=4100.0,4102.0,4101.0
        else:
            o,c,p=4102.0,4100.0,4101.0
        return {"side":None,"reason":"mtf_wait","h4_bias":"UP",
                "m5_confirm_buy":True,"m5_confirm_sell":False,
                "m15_last_open":o,"m15_last_close":c,"m15_prev_close":p}

    def test_weak_sniper_requires_m15_support(self):
        sig={"side":"BUY","mode":"NIGHT_SNIPER","score":4,"confidence":6,"reason":"x"}
        good=worker.apply_main_structure(sig,self._mtf("BUY"))
        bad=worker.apply_main_structure(sig,self._mtf("SELL"))
        self.assertEqual(good["side"],"BUY")
        self.assertIsNone(bad["side"])
        self.assertEqual(bad["reason"],"m15_confirmation_required_for_weak_sniper")

    def test_five_of_seven_cannot_fight_m15(self):
        sig={"side":"BUY","mode":"SNIPER","score":5,"confidence":6,"reason":"x"}
        bad=worker.apply_main_structure(sig,self._mtf("SELL"))
        self.assertIsNone(bad["side"])
        self.assertEqual(bad["reason"],"m15_against_medium_sniper")

    def test_six_of_seven_can_take_short_countermove(self):
        sig={"side":"BUY","mode":"SNIPER","score":6,"confidence":7,"reason":"x","target_r":1.25}
        out=worker.apply_main_structure(sig,self._mtf("SELL"))
        self.assertEqual(out["side"],"BUY")
        self.assertEqual(out["mode"],"SNIPER")


if __name__ == "__main__":
    unittest.main()