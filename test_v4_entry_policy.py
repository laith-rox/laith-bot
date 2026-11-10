import unittest
from datetime import datetime, timezone
from copy import deepcopy
from v4_entry_policy import assess_entry
from v4_quick_balance import quick_message

class EntryPolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 10, 19, 0, tzinfo=timezone.utc)
        self.d = {"atr": 4, "checks": {"BUY": [True]*7},
                  "quick5m": {"higher_side": "BUY", "ema9": 100}, "v4": {}}
        self.s = {"side": "BUY", "entry": 101, "stop": 98, "target": 105.5}
        self.r = {"time": self.now.timestamp()-10, "candle_open": 100,
                  "timing_aligned": True, "delayed_reference": False}
    def assess(self, **kw):
        return assess_entry(self.d, self.s, self.r, self.now, **kw)
    def test_live_confirmed_setup_enters_now(self):
        self.assertEqual(self.assess()["action"], "ENTER_NOW")
    def test_five_checks_enters_cautiously(self):
        self.d["checks"]["BUY"][5:] = [False, False]
        self.assertEqual(self.assess()["action"], "CAUTIOUS")
    def test_neutral_higher_can_use_local_trend_without_veto(self):
        self.d["quick5m"]["higher_side"] = "WAIT"
        self.assertEqual(self.assess()["action"], "CAUTIOUS")
        self.d["checks"]["BUY"][2] = False
        self.assertEqual(self.assess()["action"], "WATCH")
    def test_opposing_higher_stays_watch_even_seven(self):
        self.d["quick5m"]["higher_side"] = "SELL"
        self.assertEqual(self.assess()["action"], "WATCH")
    def test_external_and_structural_warnings_downgrade_not_veto(self):
        self.d["v4"] = {"macro_alignment": "CONFLICT", "intelligence": {
            "entry_gate": {"reasons": ["compressed_between_support_resistance"]}}}
        self.assertEqual(self.assess()["action"], "CAUTIOUS")
        self.assertEqual(self.assess(news_clear=False)["action"], "CAUTIOUS")
    def test_closed_reference_never_says_enter_now(self):
        self.r["delayed_reference"] = True
        self.assertEqual(self.assess()["action"], "CAUTIOUS")
    def test_stale_future_invalid_and_cached_data_block(self):
        for age in (91, -6):
            self.r["time"] = self.now.timestamp()-age
            self.assertEqual(self.assess()["action"], "WATCH")
        self.r["time"] = self.now.timestamp()
        self.assertEqual(self.assess(cached=True)["action"], "WATCH")
        self.s["entry"] = float('nan')
        self.assertEqual(self.assess()["action"], "WATCH")
    def test_stop_target_and_gap_cannot_be_outvoted(self):
        self.s["stop"] = 102
        self.assertEqual(self.assess()["action"], "WATCH")
        self.s["stop"] = 98
        self.d["v4"] = {"intelligence": {"entry_gate": {"reasons": ["recent_data_gap"]}}}
        self.assertEqual(self.assess()["action"], "WATCH")
    def test_price_chase_and_missing_momentum_wait(self):
        self.r["candle_open"] = 90
        self.assertEqual(self.assess()["action"], "WATCH")
        self.r["candle_open"] = 100
        self.d["checks"]["BUY"][0] = False
        self.assertEqual(self.assess()["action"], "WATCH")
    def test_sell_is_symmetric(self):
        self.s = {"side": "SELL", "entry": 99, "stop": 102, "target": 94.5}
        self.d["checks"] = {"SELL": [True]*7}
        self.d["quick5m"]["higher_side"] = "SELL"
        self.assertEqual(self.assess()["action"], "ENTER_NOW")
    def test_message_has_one_consistent_action(self):
        for action, phrase in (("ENTER_NOW", "ادخل الآن"), ("CAUTIOUS", "ادخل بحذر"),
                               ("WATCH", "فرصة تحت المراقبة")):
            trade = dict(self.s, entry_action=action, cautious_entry=action=="CAUTIOUS",
                         entry_policy={"reasons": ["انتظار تأكيد الحركة"]})
            text = quick_message(trade)
            self.assertIn(phrase, text)
            self.assertEqual(text.count("الحالة:"), 1)
