"""Measure decision availability without assuming HTTP requests are instantaneous."""
from datetime import timedelta
import time

EXECUTION_MODEL = 'observed-clock-v1'


class DecisionClock:
    def __init__(self, anchor, monotonic=None):
        self.anchor = anchor
        self.monotonic = monotonic or time.monotonic
        self.started = self.monotonic()

    def now(self):
        return self.anchor + timedelta(seconds=max(0, self.monotonic()-self.started))


def decision_metadata(bars, now):
    return {'decision_time': now.timestamp(),
            'source_age_at_decision_seconds': (now-bars[-1].end).total_seconds(),
            'execution_model': EXECUTION_MODEL}
