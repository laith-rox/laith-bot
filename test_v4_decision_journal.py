import unittest
from v4_decision_journal import record_candidate, journal_summary, JOURNAL_KEY

class MemoryStore:
    def __init__(self): self.data = {}
    def get(self, key): return self.data.get(key)
    def set(self, key, value): self.data[key] = value

class JournalTests(unittest.TestCase):
    def test_persist_dedupe_and_state_transition(self):
        s = MemoryStore()
        kwargs = dict(observed_at=1794000000, slot="2026-11-06T20:05", side="BUY",
                      state="WAIT", reason="await_confirmation", entry=4010, score=5)
        self.assertTrue(record_candidate(s, **kwargs))
        self.assertFalse(record_candidate(s, **kwargs))
        self.assertTrue(record_candidate(s, **{**kwargs, "state": "READY", "reason": "confirmed"}))
        self.assertEqual(len(s.get(JOURNAL_KEY)), 2)
        self.assertEqual(journal_summary(s.get(JOURNAL_KEY))["states"]["READY"], 1)
        self.assertIsNone(journal_summary(s.get(JOURNAL_KEY))["win_rate"])

    def test_bounded_history(self):
        s = MemoryStore()
        for i in range(5):
            self.assertTrue(record_candidate(s, observed_at=1794000000 + i,
                slot=str(i), side="WAIT", state="REJECTED", reason="stale", limit=3))
        self.assertEqual([e["slot"] for e in s.get(JOURNAL_KEY)], ["2", "3", "4"])

    def test_invalid_observations_fail_closed(self):
        s = MemoryStore()
        self.assertFalse(record_candidate(s, observed_at=float('nan'), slot="a",
            side="BUY", state="READY", reason="confirmed"))
        self.assertFalse(record_candidate(s, observed_at=1794000000, slot="a",
            side="BUY", state="READY", reason="confirmed", entry=float('inf')))
        self.assertIsNone(s.get(JOURNAL_KEY))

if __name__ == '__main__': unittest.main()
