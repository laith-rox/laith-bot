import unittest
from datetime import datetime, timezone

import gigi_etf


def flows_payload(latest, history=None):
    history = history or latest
    base = int(datetime(2026,9,4,tzinfo=timezone.utc).timestamp()*1000)
    def region(name, values):
        return {"name":name,"data":[[base+i*7*86400000,float(v)] for i,v in enumerate(values)]}
    names=list(gigi_etf.REGIONS)
    usd_series=[]
    tonnes_series=[]
    for name in names:
        vals=[history.get(name,0)]*3+[latest.get(name,0)]
        usd_series.append(region(name,vals))
        tonnes_series.append(region(name,[v/100_000_000 for v in vals]))
    usd_series.append(region("Gold Price (rhs)",[4200,4210,4220,4230]))
    tonnes_series.append(region("Gold Price (rhs)",[4200,4210,4220,4230]))
    return {"chartData":{"data":{"Weekly":{"series":{"usd":usd_series,"tonnes":tonnes_series}}}}}


def holdings_payload(values):
    ts=int(datetime(2026,9,25,tzinfo=timezone.utc).timestamp()*1000)
    return {"chartData":{"data":{"Weekly":{"tonnes":{
        "columns":["Date","North America","Europe","Asia","Other","Gold, US$/oz"],
        "set":[[ts,values["North America"],values["Europe"],values["Asia"],values["Other"],4293.14]],
    }}}}}


class GigiETFTests(unittest.TestCase):
    def test_broad_inflow_requires_regional_breadth(self):
        latest={"North America":1e9,"Europe":0.8e9,"Asia":0.4e9,"Other":0.1e9}
        out=gigi_etf.parse(flows_payload(latest),holdings_payload({
            "North America":2100,"Europe":1500,"Asia":530,"Other":75
        }))
        self.assertEqual(out["regime"],"BROAD_INFLOW")
        self.assertEqual(out["positive_regions"],4)
        self.assertAlmostEqual(out["holdings_tonnes"],4205.0)

    def test_mixed_week_does_not_become_broad_signal(self):
        latest={"North America":-0.6e9,"Europe":0.61e9,"Asia":0.10e9,"Other":0.03e9}
        out=gigi_etf.parse(flows_payload(latest),holdings_payload({
            "North America":2100,"Europe":1500,"Asia":530,"Other":75
        }))
        self.assertNotIn(out["regime"],("BROAD_INFLOW","BROAD_OUTFLOW"))
        self.assertEqual(out["breadth"],"WEST_AND_ASIA_INFLOW")

    def test_broad_outflow_detected(self):
        latest={"North America":-1e9,"Europe":-0.8e9,"Asia":-0.4e9,"Other":-0.1e9}
        out=gigi_etf.parse(flows_payload(latest),holdings_payload({
            "North America":2100,"Europe":1500,"Asia":530,"Other":75
        }))
        self.assertEqual(out["regime"],"BROAD_OUTFLOW")


if __name__=="__main__":
    unittest.main()
