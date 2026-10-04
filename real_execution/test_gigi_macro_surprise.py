import unittest

import gigi_macro_surprise


class GigiMacroSurpriseTests(unittest.TestCase):
    def test_units_parse(self):
        self.assertEqual(gigi_macro_surprise.parse_number("250K"),250000)
        self.assertEqual(gigi_macro_surprise.parse_number("-95.2B"),-95.2e9)
        self.assertAlmostEqual(gigi_macro_surprise.parse_number("0.3%"),0.3)

    def test_hot_cpi_is_usd_positive_textbook(self):
        event={"title":"CPI m/m","event_class":"CPI","actual":"0.4%","forecast":"0.3%"}
        out=gigi_macro_surprise.event_surprise(event)
        self.assertEqual(out["usd_surprise"],"USD_POSITIVE")
        self.assertEqual(out["gold_textbook_pressure"],"BEARISH_TEXTBOOK")

    def test_higher_unemployment_is_usd_negative(self):
        event={"title":"Unemployment Rate","event_class":"LABOR_NFP","actual":"4.5%","forecast":"4.3%"}
        out=gigi_macro_surprise.event_surprise(event)
        self.assertEqual(out["usd_surprise"],"USD_NEGATIVE")

    def test_gold_can_reject_textbook_macro_direction(self):
        macro={"event_bundle":[{
            "title":"CPI m/m","event_class":"CPI","actual":"0.4%","forecast":"0.3%"
        }]}
        out=gigi_macro_surprise.analyze(macro,{"impulse":"BULLISH"})
        self.assertEqual(out["bundle_surprise"],"USD_POSITIVE")
        self.assertEqual(out["price_relation"],"GOLD_REJECTED_USD_POSITIVE_SURPRISE")
        self.assertFalse(out["directional_signal"])

    def test_missing_actual_stays_unknown(self):
        event={"title":"CPI m/m","event_class":"CPI","actual":"","forecast":"0.3%"}
        out=gigi_macro_surprise.event_surprise(event)
        self.assertEqual(out["status"],"UNAVAILABLE")


if __name__=="__main__":
    unittest.main()
