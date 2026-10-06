import unittest

import gigi_central_banks


ARCHIVE = """
<a href="/goldhub/gold-focus/2026/09/central-bank-gold-statistics-central-banks-make-positive-headlines-gold">
Central Bank Gold Statistics</a>
"""

ARTICLE = """
<script type="application/ld+json">{"datePublished":"2026-09-03T08:00:00+01:00"}</script>
<p>Central banks continued their gold accumulation in July with net buying reported at 23t.</p>
<p>On a y-t-d basis, central banks reported purchases have totalled around 130t of gold.</p>
<p>*Data to 31 July 2026, where available.</p>
"""


class GigiCentralBankTests(unittest.TestCase):
    def test_discover_latest_article_link(self):
        url = gigi_central_banks.discover_article(ARCHIVE)
        self.assertTrue(url.endswith("central-bank-gold-statistics-central-banks-make-positive-headlines-gold"))

    def test_parse_monthly_and_ytd_buying(self):
        out = gigi_central_banks.parse_article(ARTICLE, "https://example.test")
        self.assertEqual(out["regime"], "NET_BUYING")
        self.assertEqual(out["monthly_net_tonnes"], 23.0)
        self.assertEqual(out["ytd_reported_tonnes"], 130.0)
        self.assertEqual(out["published_date"], "2026-09-03")
        self.assertFalse(out["directional_signal"])

    def test_strong_buying_classification(self):
        out = gigi_central_banks.parse_article(
            "<p>Central banks bought a net 51t of gold.</p>"
        )
        self.assertEqual(out["regime"], "STRONG_NET_BUYING")

    def test_missing_flow_fails_unknown(self):
        out = gigi_central_banks.parse_article("<p>No monthly total here.</p>")
        self.assertEqual(out["regime"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
