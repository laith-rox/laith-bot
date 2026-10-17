import unittest

import gigi_entry_timing


def rows(step=0.1,n=30,last_range=None):
    out=[]
    price=100.0
    for i in range(n):
        o=price
        c=price+step
        hi=max(o,c)+0.05
        lo=min(o,c)-0.05
        out.append({"open":o,"high":hi,"low":lo,"close":c})
        price=c
    if last_range is not None:
        mid=out[-1]["close"]
        out[-1]["high"]=mid+last_range/2
        out[-1]["low"]=mid-last_range/2
    return out


class GigiEntryTimingTests(unittest.TestCase):
    def test_stretched_move_flags_chase_risk(self):
        data=rows(step=0.6,n=30)
        out=gigi_entry_timing.assess(
            {"side":"BUY"},data,
            {"extension_state":"EXTENDED","vwap_distance_atr":1.8,"range_event":"INSIDE"},
            {"event":"NONE"},
            {"state":"REALIZED_EXPANSION"},
        )
        self.assertEqual(out["state"],"CHASE_RISK")
        self.assertEqual(out["posture"],"WAIT_FOR_RETEST_SHADOW")
        self.assertFalse(out["execution_gate"])

    def test_matching_liquidity_sweep_is_separate_from_chase(self):
        data=rows(step=0.05,n=30)
        out=gigi_entry_timing.assess(
            {"side":"BUY"},data,
            {"extension_state":"MODERATE","vwap_distance_atr":0.6,"range_event":"FAILED_BREAK_BELOW"},
            {"event":"SELL_SIDE_SWEEP"},
            {"state":"NORMAL"},
        )
        self.assertEqual(out["state"],"LIQUIDITY_RETEST")
        self.assertTrue(out["matching_liquidity_sweep"])

    def test_accepted_breakout_can_be_clean_timing(self):
        data=rows(step=0.08,n=30)
        out=gigi_entry_timing.assess(
            {"side":"BUY"},data,
            {"extension_state":"MODERATE","vwap_distance_atr":0.7,"range_event":"ACCEPTED_ABOVE"},
            {"event":"NONE"},
            {"state":"NORMAL"},
        )
        self.assertEqual(out["state"],"BREAKOUT_ACCEPTANCE")

    def test_short_data_fails_unknown(self):
        out=gigi_entry_timing.assess({"side":"SELL"},[],{}, {}, {})
        self.assertEqual(out["state"],"UNKNOWN")


if __name__=="__main__":
    unittest.main()
