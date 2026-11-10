import unittest
from v4_opportunity_plan import build_manual_plan, OpportunityState


class ManualPlanTests(unittest.TestCase):
    def plan(self, **kwargs):
        defaults = dict(confirmed=True, quote_fresh=True, session_open=True, news_safe=True)
        defaults.update(kwargs)
        return build_manual_plan("BUY", "SCALP", 3000, 2998, 3004, **defaults)

    def test_ready(self):
        self.assertEqual(self.plan().state, OpportunityState.READY)

    def test_wait_for_confirmation(self):
        self.assertEqual(self.plan(confirmed=False).state, OpportunityState.WATCH)

    def test_closed_market(self):
        self.assertEqual(self.plan(session_open=False).state, OpportunityState.INVALID)

    def test_unverified_quote(self):
        self.assertEqual(self.plan(quote_fresh=False).state, OpportunityState.INVALID)

    def test_news_risk(self):
        self.assertEqual(self.plan(news_safe=False).state, OpportunityState.WATCH)

    def test_bad_reward_to_risk(self):
        self.assertEqual(self.plan(minimum_rr=3).state, OpportunityState.INVALID)

    def test_bad_buy_geometry(self):
        with self.assertRaises(ValueError):
            build_manual_plan("BUY", "SCALP", 3000, 3002, 3004)

    def test_sell(self):
        result = build_manual_plan("SELL", "INTRADAY", 3000, 3002, 2996,
                                   confirmed=True, quote_fresh=True,
                                   session_open=True, news_safe=True)
        self.assertEqual(result.state, OpportunityState.READY)

if __name__ == "__main__":
    unittest.main()
