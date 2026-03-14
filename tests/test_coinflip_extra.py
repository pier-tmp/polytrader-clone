"""
Extra edge-case tests for the Coinflip filter.
Run with: pytest tests/test_coinflip_extra.py
"""
import pytest
from datetime import datetime, timezone, timedelta

from src.models import TradeSignal, Leader, Market
from src.guards.coinflip_filter import is_coinflip


def _make_signal(question="Test?", tags=None, end_date=None):
    leader = Leader(wallet="0x1", name="T", win_rate=70, volume_usd=10000)
    market = Market(
        condition_id="c1",
        token_id="t1",
        question=question,
        tags=tags or [],
        end_date=end_date,
    )
    return TradeSignal(leader=leader, market=market, side="BUY")


class TestCoinflipEdgeCases:

    def test_crypto_no_end_date_no_keyword_passes(self):
        """Crypto market without end_date and without coinflip keywords should pass."""
        sig = _make_signal("Will Bitcoin reach $200k?", tags=["crypto"])
        assert is_coinflip(sig) is False

    def test_crypto_long_title_with_keyword(self):
        sig = _make_signal(
            "In the next 5-minute window, will BTC go up?", tags=["crypto"]
        )
        assert is_coinflip(sig) is True

    def test_non_crypto_short_expiry_passes(self):
        """Non-crypto market with short expiry should NOT be blocked."""
        end = datetime.now(timezone.utc) + timedelta(minutes=10)
        sig = _make_signal("Will the vote pass?", tags=["politics"], end_date=end)
        assert is_coinflip(sig) is False

    def test_crypto_exactly_30_min_passes(self):
        """30 minutes is the boundary — exactly 30 min should pass (< 30 blocks)."""
        end = datetime.now(timezone.utc) + timedelta(minutes=30)
        sig = _make_signal("Will ETH go up?", tags=["crypto"], end_date=end)
        # "will eth go up" matches COINFLIP_PATTERNS so this gets blocked by title
        assert is_coinflip(sig) is True

    def test_crypto_31_min_no_keyword_passes(self):
        end = datetime.now(timezone.utc) + timedelta(minutes=31)
        sig = _make_signal("Will SOL reach $300?", tags=["crypto"], end_date=end)
        assert is_coinflip(sig) is False

    def test_case_insensitive_tags(self):
        sig = _make_signal("Will BTC hit 100k?", tags=["CRYPTO"])
        # "CRYPTO" should match since tags are lowered
        end = datetime.now(timezone.utc) + timedelta(minutes=5)
        sig2 = _make_signal("Will BTC hit 100k?", tags=["CRYPTO"], end_date=end)
        assert is_coinflip(sig2) is True

    def test_naive_end_date_handled(self):
        """end_date without tzinfo should still work (gets replaced with utc)."""
        end = datetime.now() + timedelta(minutes=5)  # naive
        sig = _make_signal("Will SOL go up?", tags=["crypto"], end_date=end)
        assert is_coinflip(sig) is True

    def test_empty_title_passes(self):
        sig = _make_signal("", tags=["politics"])
        assert is_coinflip(sig) is False

    def test_up_down_pattern(self):
        sig = _make_signal("Bitcoin up/down next candle?", tags=["btc"])
        assert is_coinflip(sig) is True
