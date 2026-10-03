import unittest
from datetime import datetime, timezone, timedelta

import gigi_volatility


def rows(values):
    t0=datetime(2026,10,1,tzinfo=timezone.utc)
    return [{
        "datetime":(t0+timedelta(minutes=15*i)).isoformat(),
        "open":float(v),
        "high":float(v)*1.001,
        "low":float(v)*0.999,
        "close":float(v),
    } for i,v in enumerate(values)]


class GigiVolatilityTests(unittest.TestCase):
    def test_gvz_parser_labels_proxy(self):
        lines=["DATE,GVZ"]
        base=datetime(2025,1,1)
        for i in range(260):
            date=(base+timedelta(days=i)).strftime("%m/%d/%Y")
            value=15.0 + i*0.02
            lines.append(f"{date},{value:.2f}")
        out=gigi_volatility.parse_gvz_csv("\n".join(lines))
        self.assertEqual(out["gvz_regime"],"ELEVATED")
        self.assertIn("GLD_options",out["proxy_note"])

    def test_realised_expansion_detected(self):
        values=[100.0]
        for i in range(80):
            step=0.03 if i < 64 else (0.80 if i%2==0 else -0.75)
            values.append(max(1.0,values[-1]+step))
        out=gigi_volatility.realised_context(rows(values))
        self.assertIn(out["rv_state"],("EXPANDING","EXPLOSIVE"))
        self.assertGreater(out["rv_ratio"],1.0)

    def test_compression_plus_high_gvz_is_priced_move_compression(self):
        values=[100.0]
        for i in range(80):
            step=(0.6 if i%2==0 else -0.55) if i < 64 else (0.02 if i%2==0 else -0.02)
            values.append(max(1.0,values[-1]+step))
        out=gigi_volatility.analyze(
            rows(values),
            {"gvz_regime":"ELEVATED","gvz":31.0,"source":"TEST"},
        )
        self.assertEqual(out["state"],"PRICED_MOVE_COMPRESSION")
        self.assertFalse(out["directional_signal"])

    def test_short_data_is_unknown(self):
        out=gigi_volatility.realised_context([])
        self.assertEqual(out["rv_state"],"UNKNOWN")


if __name__=="__main__":
    unittest.main()
