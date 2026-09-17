import os
import unittest
from unittest.mock import patch

from v4_key_config import apply_v4_twelve_key_precedence, select_v4_twelve_key
from v4_runtime import parser


class V4KeyConfigTests(unittest.TestCase):
    def test_dedicated_v4_key_wins_over_shared_key(self):
        key, source = select_v4_twelve_key({
            "V4_TWELVE_DATA_API_KEY": "v4-key",
            "TWELVE_DATA_API_KEY": "shared-key",
        })
        self.assertEqual(key, "v4-key")
        self.assertEqual(source, "V4_TWELVE_DATA_API_KEY")

    def test_shared_key_is_fallback(self):
        key, source = select_v4_twelve_key({"TWELVE_DATA_API_KEY": "shared-key"})
        self.assertEqual(key, "shared-key")
        self.assertEqual(source, "TWELVE_DATA_API_KEY")

    def test_apply_makes_existing_parser_use_dedicated_key(self):
        with patch.dict(os.environ, {
            "V4_TWELVE_DATA_API_KEY": "v4-key",
            "TWELVE_DATA_API_KEY": "shared-key",
        }, clear=False):
            source = apply_v4_twelve_key_precedence()
            args = parser().parse_args([])
            self.assertEqual(source, "V4_TWELVE_DATA_API_KEY")
            self.assertEqual(args.twelve_key, "v4-key")

    def test_missing_keys_stay_missing(self):
        key, source = select_v4_twelve_key({})
        self.assertIsNone(key)
        self.assertEqual(source, "missing")


if __name__ == "__main__":
    unittest.main()
