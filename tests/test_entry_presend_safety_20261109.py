"""Fail-closed regression checks for entry messages immediately before Telegram send.

No broker calls or Telegram network calls are made by these tests.
"""
import unittest
from unittest.mock import Mock
from transport import dispatch


class EntryPresendSafetyTests(unittest.TestCase):
    def setUp(self):
        self.store = Mock()
        self.store.claim.side_effect = [
            {"id": 11, "kind": "entry", "signal_id": 7, "message": "BUY"},
            None,
        ]
        self.store.trade.return_value = {
            "id": 7, "quote_time": 1000, "entry_expires": 1100,
            "entry": 3000.0, "price_tolerance": 2.0,
        }
        self.store.reply_target.return_value = None
        self.telegram = Mock()
        self.telegram.send.return_value = Mock(
            status="sent", message_id=44, error=None, retry_after=0
        )
        self.market = Mock()
        self.market.quote.return_value = {"price": 3000.5, "time": 1049}

    def test_market_unavailable_blocks_entry(self):
        dispatch(self.store, self.telegram, now=1050, market=None)
        self.telegram.send.assert_not_called()
        self.store.finish.assert_called_once_with(
            11, "failed", 1050, error="market_quote_unavailable"
        )

    def test_expired_entry_blocks_even_with_matching_price(self):
        dispatch(self.store, self.telegram, now=1100, market=self.market)
        self.telegram.send.assert_not_called()
        self.store.finish.assert_called_once_with(
            11, "failed", 1100, error="market_quote_stale"
        )

    def test_moved_price_blocks_entry(self):
        self.market.quote.return_value = {"price": 3002.01, "time": 1049}
        dispatch(self.store, self.telegram, now=1050, market=self.market)
        self.telegram.send.assert_not_called()
        self.store.finish.assert_called_once_with(
            11, "failed", 1050, error="market_price_moved"
        )

    def test_valid_entry_can_send(self):
        dispatch(self.store, self.telegram, now=1050, market=self.market)
        self.telegram.send.assert_called_once_with("BUY")
        self.store.finish.assert_called_once_with(
            11, "sent", 1050, 44, None, 0
        )

    def test_missing_original_quote_blocks_entry(self):
        self.store.trade.return_value["quote_time"] = None
        dispatch(self.store, self.telegram, now=1050, market=self.market)
        self.telegram.send.assert_not_called()
        self.market.quote.assert_not_called()


if __name__ == "__main__":
    unittest.main()
