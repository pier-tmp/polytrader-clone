"""
Unit tests for guards, models, and core logic.
Run with: pytest tests/
"""
import pytest
from datetime import datetime, timezone, timedelta

from src.models import TradeSignal, Leader, Market, Position
from src.guards.coinflip_filter import is_coinflip
from src.guards.sports_aware import is_sports_market, is_sports_trailing_stop_exempt


# ── Fixtures ──────────────────────────────────────────────

def make_signal(
    question="Will candidate X win?",
    tags=None,
    side="BUY",
    end_date=None,
    price=0.5,
):
    leader = Leader(wallet="0x1234", name="TestLeader", win_rate=65, volume_usd=10000)
    market = Market(
        condition_id="cond123",
        token_id="tok123",
        question=question,
        slug="candidate-x-win",
        tags=tags or [],
        end_date=end_date,
        volume_24h=50000,
        liquidity=100000,
    )
    return TradeSignal(leader=leader, market=market, side=side, price=price)


# ── Coinflip Filter Tests ────────────────────────────────

class TestCoinflipFilter:

    def test_blocks_btc_5min(self):
        sig = make_signal("Will BTC go up in the next 5-minute window?", tags=["crypto"])
        assert is_coinflip(sig) is True

    def test_blocks_eth_15min(self):
        sig = make_signal("Will ETH be above $2000 in 15-minute speed market?", tags=["eth"])
        assert is_coinflip(sig) is True

    def test_blocks_up_down(self):
        sig = make_signal("Bitcoin up or down next hour?", tags=["btc"])
        assert is_coinflip(sig) is True

    def test_allows_politics(self):
        sig = make_signal("Will candidate X win the election?", tags=["politics"])
        assert is_coinflip(sig) is False

    def test_blocks_crypto_short_expiry(self):
        end = datetime.now(timezone.utc) + timedelta(minutes=10)
        sig = make_signal("Will SOL reach $150?", tags=["crypto"], end_date=end)
        assert is_coinflip(sig) is True

    def test_allows_crypto_long_expiry(self):
        end = datetime.now(timezone.utc) + timedelta(days=30)
        sig = make_signal("Will Bitcoin reach $100k by end of year?", tags=["crypto"], end_date=end)
        assert is_coinflip(sig) is False

    def test_allows_sports(self):
        sig = make_signal("Will Lakers win tonight?", tags=["nba", "sports"])
        assert is_coinflip(sig) is False


# ── Sports-Aware Tests ────────────────────────────────────

class TestSportsAware:

    def test_detects_nba(self):
        sig = make_signal("Lakers vs Celtics", tags=["nba", "sports"])
        assert is_sports_market(sig) is True

    def test_detects_soccer_by_title(self):
        sig = make_signal("Will Arsenal win the Premier League?", tags=[])
        assert is_sports_market(sig) is True

    def test_not_sports(self):
        sig = make_signal("Will inflation drop below 3%?", tags=["economics"])
        assert is_sports_market(sig) is False

    def test_sports_exempt_from_trailing_stop(self):
        sig = make_signal("NBA Finals winner", tags=["nba"])
        assert is_sports_trailing_stop_exempt(sig) is True

    def test_non_sports_not_exempt(self):
        sig = make_signal("Fed rate decision", tags=["economics"])
        assert is_sports_trailing_stop_exempt(sig) is False


# ── Position Model Tests ─────────────────────────────────

class TestPosition:

    def test_pnl_calculation_profit(self):
        pos = Position(entry_price=0.40, size=100, high_price=0.40)
        pos.update_pnl(0.55)
        assert pos.pnl_usd == pytest.approx(15.0)
        assert pos.high_price == 0.55

    def test_pnl_calculation_loss(self):
        pos = Position(entry_price=0.60, size=50, high_price=0.60)
        pos.update_pnl(0.45)
        assert pos.pnl_usd == pytest.approx(-7.5)
        assert pos.high_price == 0.60  # unchanged

    def test_high_price_tracks_peak(self):
        pos = Position(entry_price=0.30, size=100, high_price=0.30)
        pos.update_pnl(0.50)
        assert pos.high_price == 0.50
        pos.update_pnl(0.45)
        assert pos.high_price == 0.50  # doesn't drop
        pos.update_pnl(0.60)
        assert pos.high_price == 0.60  # new peak
