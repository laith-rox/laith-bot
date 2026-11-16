import unittest
from v4_telegram import quick_message


class RoyalQuickCardTests(unittest.TestCase):
    def sample(self, **overrides):
        data = dict(side="SELL", strength="متوسطة", score=7, stop=3877.94,
                    entry=3875.94, target=3872.94, buy_score=0,
                    sell_score=7, risk_level="مرتفعة", delayed_reference=True,
                    entry_action="CAUTIOUS", risk_reasons=["شرح طويل مكرر"])
        data.update(overrides)
        return data

    def test_royal_layout_and_prices(self):
        text = quick_message(self.sample())
        self.assertIn("BLACK DIAMOND ROYAL", text)
        self.assertLess(text.index("STOP"), text.index("ENTRY"))
        self.assertLess(text.index("ENTRY"), text.index("TARGET"))
        self.assertIn("3875.94", text)
        self.assertIn("بيع <b>7/7</b>", text)

    def test_stale_price_warning_is_concise_and_not_removed(self):
        text = quick_message(self.sample())
        self.assertEqual(text.count("ليس سعرًا حيًا"), 1)
        self.assertNotIn("شرح طويل مكرر", text)
        self.assertIn("إشارة ورقية غير مضمونة", text)

    def test_live_reference_is_not_misrepresented(self):
        text = quick_message(self.sample(delayed_reference=False, entry_action="WATCH"))
        self.assertNotIn("آخر شمعة M5 مغلقة", text)
        self.assertIn("تحت المراقبة", text)

    def test_cautious_and_enter_now_remain_distinct(self):
        self.assertIn("ادخل بحذر", quick_message(self.sample()))
        self.assertIn("ادخل الآن", quick_message(self.sample(entry_action="ENTER_NOW")))


if __name__ == "__main__":
    unittest.main()
