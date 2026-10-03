import unittest

import gigi_learning


class GigiLearningTests(unittest.TestCase):
    def observation(self, idx, close_r=1.0, **overrides):
        row = {
            "id": f"obs-{idx}",
            "resolved": True,
            "close_r": close_r,
            "mfe_r": max(0.0, close_r + 0.5),
            "mae_r": min(0.0, close_r - 0.5),
            "mode": "SNIPER",
            "regime": "TREND_UP",
            "alignment": "SUPPORT",
            "macro_regime": "CLEAR",
            "intermarket_bias": "BULLISH_GOLD",
            "session": "DAY_SNIPER",
            "strength": "S5",
        }
        row.update(overrides)
        return row

    def test_small_sample_never_calibrates(self):
        state = gigi_learning.new_state()
        for i in range(5):
            gigi_learning.record(state, self.observation(i))
        bucket = gigi_learning.report(state)["buckets"]["mode:SNIPER"]
        self.assertEqual(bucket["status"], "INSUFFICIENT_SAMPLE")
        self.assertEqual(gigi_learning.shadow_weight(state, "mode", "SNIPER"), 0.0)

    def test_bucket_calibrates_after_minimum_sample(self):
        state = gigi_learning.new_state()
        for i in range(gigi_learning.MIN_BUCKET_SAMPLES):
            gigi_learning.record(state, self.observation(i, 1.0 if i % 2 == 0 else -0.5))
        bucket = gigi_learning.report(state)["buckets"]["mode:SNIPER"]
        self.assertEqual(bucket["status"], "CALIBRATED")
        self.assertEqual(bucket["n"], gigi_learning.MIN_BUCKET_SAMPLES)

    def test_duplicate_observation_is_idempotent(self):
        state = gigi_learning.new_state()
        obs = self.observation(1)
        gigi_learning.record(state, obs)
        gigi_learning.record(state, obs)
        self.assertEqual(state["resolved"], 1)
        self.assertEqual(state["buckets"]["mode:SNIPER"]["n"], 1)

    def test_shadow_weight_is_bounded(self):
        state = gigi_learning.new_state()
        for i in range(gigi_learning.MIN_WEIGHT_SAMPLES):
            gigi_learning.record(state, self.observation(i, close_r=20.0))
        self.assertLessEqual(
            abs(gigi_learning.shadow_weight(state, "mode", "SNIPER")),
            gigi_learning.MAX_SHADOW_WEIGHT,
        )

    def test_score_is_observation_not_probability(self):
        state = gigi_learning.new_state()
        gigi_learning.record(state, self.observation(1, strength="S7"))
        self.assertEqual(gigi_learning.report(state)["note"], "shadow_learning_only_not_probability")


if __name__ == "__main__":
    unittest.main()
