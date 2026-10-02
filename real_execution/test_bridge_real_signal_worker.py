import os
import unittest

os.environ["REAL_SIGNAL_ENABLED"] = "false"
os.environ["REAL_VOLUME"] = "0"
os.environ["REAL_MAX_PUBLISH_PER_HOUR"] = "0"
os.environ.pop("REAL_BRIDGE_URL", None)
os.environ.pop("REAL_BRIDGE_PUBLISH_TOKEN", None)

import bridge_real_signal_worker as worker


class StopDisabledLoop(Exception):
    pass


class RealSignalFailClosedTests(unittest.TestCase):
    def test_defaults_are_disabled(self):
        self.assertFalse(worker.REAL_SIGNAL_ENABLED)
        self.assertEqual(worker.VOLUME, 0.0)
        self.assertEqual(worker.MAX_PUBLISH_PER_HOUR, 0)
        self.assertEqual(worker.config_reason(), "real_signal_disabled")

    def test_disabled_worker_never_contacts_bridge(self):
        original_sleep = worker.time.sleep
        original_health = worker.bridge_health

        def stop_sleep(_seconds):
            raise StopDisabledLoop()

        def forbidden_health():
            raise AssertionError("disabled REAL worker must not contact bridge")

        worker.time.sleep = stop_sleep
        worker.bridge_health = forbidden_health
        try:
            with self.assertRaises(StopDisabledLoop):
                worker.run_forever()
        finally:
            worker.time.sleep = original_sleep
            worker.bridge_health = original_health


if __name__ == "__main__":
    unittest.main()
