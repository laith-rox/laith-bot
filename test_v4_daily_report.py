import unittest
from datetime import datetime, timezone
from v4_daily_report import plan_daily_decision_report

UTC = timezone.utc

class DailyReportTests(unittest.TestCase):
    def test_previous_local_day_only(self):
        now = datetime(2026, 11, 7, 7, 0, tzinfo=UTC)
        events = [
            {"observed_at": "2026-11-06T21:30:00+00:00", "state": "READY", "reason": "confirmed"},
            {"observed_at": "2026-11-06T19:30:00+00:00", "state": "REJECTED", "reason": "stale"},
            {"observed_at": "2026-11-07T04:00:00+00:00", "state": "WAIT", "reason": "waiting"},
        ]
        result = plan_daily_decision_report(now, events)
        self.assertEqual(result["key"], "v4_daily_decisions:2026-11-06")
        self.assertIn("جاهزة: 1", result["message"])
        self.assertIn("مرفوضة: 1", result["message"])
        self.assertNotIn("نسبة نجاح: 100", result["message"])

    def test_telegram_html_escapes_untrusted_block_reasons(self):
        now = datetime(2026, 11, 7, 8, tzinfo=UTC)
        events = [{"observed_at": "2026-11-06T19:30:00Z",
                   "state": "WAIT", "reason": "<b>spoofed</b> & \"fake\""}]
        message = plan_daily_decision_report(now, events)["message"]
        self.assertIn("&lt;b&gt;spoofed&lt;/b&gt; &amp; &quot;fake&quot;", message)
        self.assertNotIn("<b>spoofed</b>", message)

    def test_quiet_before_morning_and_empty(self):
        events = [{"observed_at": "2026-11-06T19:30:00Z", "state": "READY", "reason": "ok"}]
        self.assertIsNone(plan_daily_decision_report(datetime(2026,11,7,3,tzinfo=UTC),events))
        self.assertIsNone(plan_daily_decision_report(datetime(2026,11,7,8,tzinfo=UTC),[]))

    def test_reject_future_and_bad_rows(self):
        now = datetime(2026,11,7,8,tzinfo=UTC)
        events = [{"observed_at":"2026-11-08T10:00:00Z", "state":"READY", "reason":"future"},
                  {"observed_at":"not-a-date", "state":"READY", "reason":"bad"}]
        self.assertIsNone(plan_daily_decision_report(now,events))
        with self.assertRaises(ValueError):
            plan_daily_decision_report(datetime(2026,11,7,8),events)


class ReportDeliveryTests(unittest.TestCase):
    def test_delivery_once_and_retry_on_failure(self):
        from v4_alert_coordinator import run_alert_cycle
        class Store:
            def __init__(self): self.data = {}
            def get(self, key): return self.data.get(key)
            def set(self, key, value): self.data[key] = value
        class Notifier:
            def __init__(self): self.messages = []; self.ok = False
            def send(self, message):
                self.messages.append(message)
                return self.ok
        now = datetime(2026,11,7,8,tzinfo=UTC)
        events = [{"observed_at":"2026-11-06T19:30:00Z", "state":"READY", "reason":"confirmed"}]
        s, n = Store(), Notifier()
        kwargs = dict(store=s, notifier=n, broker_sessions=(), quote_at=None,
                      decision_events=events)
        self.assertEqual(run_alert_cycle(now, **kwargs), [])
        n.ok = True
        self.assertEqual(run_alert_cycle(now, **kwargs), ["v4_daily_decisions:2026-11-06"])
        self.assertEqual(run_alert_cycle(now, **kwargs), [])
        self.assertEqual(len(n.messages), 2)

if __name__ == '__main__': unittest.main()
