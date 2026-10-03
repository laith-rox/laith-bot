import unittest

from gigi_profit_protection import desired_lock_usd, main_lock_usd, sniper_lock_usd


class GigiProfitProtectionTests(unittest.TestCase):
    def test_sniper_locks_profit_progressively(self):
        self.assertIsNone(sniper_lock_usd(1.99))
        self.assertEqual(sniper_lock_usd(2.00), 1.0)
        self.assertEqual(sniper_lock_usd(4.00), 2.0)
        self.assertEqual(sniper_lock_usd(6.00), 4.0)
        self.assertEqual(sniper_lock_usd(8.00), 6.0)

    def test_main_secures_entry_at_one_r(self):
        self.assertIsNone(main_lock_usd(2.99, 3.0))
        self.assertGreater(main_lock_usd(3.0, 3.0), 0.0)

    def test_main_trails_as_profit_expands(self):
        lock_1r = main_lock_usd(3.0, 3.0)
        lock_2r = main_lock_usd(6.0, 3.0)
        lock_3r = main_lock_usd(9.0, 3.0)
        self.assertGreater(lock_2r, lock_1r)
        self.assertGreater(lock_3r, lock_2r)

    def test_dispatch_by_mode(self):
        self.assertEqual(desired_lock_usd("SNIPER", 4.0, 9.0), 2.0)
        self.assertEqual(desired_lock_usd("MAIN", 6.0, 3.0), main_lock_usd(6.0, 3.0))


if __name__ == "__main__":
    unittest.main()
