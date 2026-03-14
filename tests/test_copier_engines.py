"""
Unit tests for PaperEngine and LiveEngine.
Run with: pytest tests/test_copier_engines.py
"""
import pytest
from unittest.mock import MagicMock, patch

from src.models import TradeSignal, Leader, Market, Position
from src.copier.paper_engine import PaperEngine
from src.copier.live_engine import LiveEngine


# ── Helpers ──────────────────────────────────────────────

def _make_signal(side="BUY", token_id="tok_abc"):
    leader = Leader(wallet="0xLeader", name="Alice", win_rate=70, volume_usd=50000)
    market = Market(
        condition_id="cond1",
        token_id=token_id,
        question="Will X happen?",
        slug="will-x-happen",
        tags=["politics"],
        volume_24h=100000,
        liquidity=200000,
    )
    return TradeSignal(leader=leader, market=market, side=side, token_id=token_id)


def _make_open_position(entry_price=0.50, size=100.0, token_id="tok_abc"):
    return Position(
        id=1,
        market_slug="will-x-happen",
        token_id=token_id,
        side="BUY",
        entry_price=entry_price,
        size=size,
        cost_usd=entry_price * size,
        current_price=entry_price,
        high_price=entry_price,
        leader_wallet="0xLeader",
        is_paper=True,
        status="OPEN",
    )


def _mock_deps(fill_price=0.50, sell_price=0.55, midpoint=0.50):
    """Create mocked ClobClient and Storage."""
    clob = MagicMock()
    clob.estimate_fill_price.return_value = fill_price
    clob.get_price.return_value = sell_price
    clob.get_midpoint.return_value = midpoint

    storage = MagicMock()
    storage.get_open_positions.return_value = []
    storage.get_pnl_summary.return_value = {"total_pnl": 0}
    return clob, storage


# ── PaperEngine Tests ───────────────────────────────────

class TestPaperEngineBuy:

    def test_buy_creates_position(self):
        clob, storage = _mock_deps(fill_price=0.50)
        engine = PaperEngine(clob, storage)
        sig = _make_signal()

        pos = engine.execute_buy(sig)

        assert pos is not None
        assert pos.side == "BUY"
        assert pos.entry_price == 0.50
        assert pos.is_paper is True
        assert pos.status == "OPEN"
        storage.save_trade.assert_called_once()
        storage.save_position.assert_called_once()

    def test_buy_calculates_shares(self):
        clob, storage = _mock_deps(fill_price=0.40)
        engine = PaperEngine(clob, storage)
        sig = _make_signal()

        pos = engine.execute_buy(sig)

        # bankroll=1000, bet_size=5% → budget=50, price=0.40 → 125 shares
        assert pos is not None
        assert pos.size == pytest.approx(125.0)
        assert pos.cost_usd == pytest.approx(50.0)

    def test_buy_returns_none_when_bankroll_too_low(self):
        clob, storage = _mock_deps()
        storage.get_open_positions.return_value = []
        storage.get_pnl_summary.return_value = {"total_pnl": -999}
        engine = PaperEngine(clob, storage)
        engine._bankroll = 0.50  # too low

        pos = engine.execute_buy(_make_signal())

        assert pos is None
        storage.save_trade.assert_not_called()

    def test_buy_returns_none_when_fill_price_zero(self):
        clob, storage = _mock_deps(fill_price=0)
        engine = PaperEngine(clob, storage)

        pos = engine.execute_buy(_make_signal())

        assert pos is None
        storage.save_trade.assert_not_called()

    def test_buy_uses_signal_token_id(self):
        clob, storage = _mock_deps(fill_price=0.60)
        engine = PaperEngine(clob, storage)
        sig = _make_signal(token_id="tok_custom")

        pos = engine.execute_buy(sig)

        assert pos.token_id == "tok_custom"
        clob.estimate_fill_price.assert_called_once_with("tok_custom", "BUY", pytest.approx(50.0))


class TestPaperEngineSell:

    def test_sell_closes_position(self):
        clob, storage = _mock_deps(sell_price=0.60)
        engine = PaperEngine(clob, storage)
        pos = _make_open_position(entry_price=0.50, size=100)

        pnl = engine.execute_sell(pos, reason="trailing_stop")

        assert pos.status == "CLOSED"
        assert pos.close_reason == "trailing_stop"
        assert pos.closed_at is not None
        assert pnl == pytest.approx(10.0)  # (0.60 - 0.50) * 100
        storage.save_position.assert_called_once()
        storage.save_trade.assert_called_once()

    def test_sell_negative_pnl(self):
        clob, storage = _mock_deps(sell_price=0.40)
        engine = PaperEngine(clob, storage)
        pos = _make_open_position(entry_price=0.50, size=100)

        pnl = engine.execute_sell(pos)

        assert pnl == pytest.approx(-10.0)

    def test_sell_falls_back_to_midpoint(self):
        clob, storage = _mock_deps(sell_price=0, midpoint=0.55)
        engine = PaperEngine(clob, storage)
        pos = _make_open_position(entry_price=0.50, size=100)

        pnl = engine.execute_sell(pos)

        clob.get_midpoint.assert_called_once()
        assert pnl == pytest.approx(5.0)


class TestPaperBankroll:

    def test_bankroll_full_when_no_positions(self):
        clob, storage = _mock_deps()
        engine = PaperEngine(clob, storage)

        assert engine.bankroll == pytest.approx(1000.0)

    def test_bankroll_subtracts_invested(self):
        clob, storage = _mock_deps()
        open_pos = _make_open_position(entry_price=0.50, size=100)
        storage.get_open_positions.return_value = [open_pos]
        engine = PaperEngine(clob, storage)

        assert engine.bankroll == pytest.approx(1000.0 - 50.0)

    def test_bankroll_adds_realized_pnl(self):
        clob, storage = _mock_deps()
        storage.get_pnl_summary.return_value = {"total_pnl": 25.0}
        engine = PaperEngine(clob, storage)

        assert engine.bankroll == pytest.approx(1025.0)


# ── LiveEngine Tests ────────────────────────────────────

class TestLiveEngineBuy:

    def test_buy_matched_creates_position(self):
        clob, storage = _mock_deps(midpoint=0.50)
        clob.place_limit_order.return_value = {"orderID": "ord_1", "status": "MATCHED"}
        engine = LiveEngine(clob, storage)

        with patch.object(type(engine), "bankroll", new_callable=lambda: property(lambda self: 1000.0)):
            pos = engine.execute_buy(_make_signal())

        assert pos is not None
        assert pos.is_paper is False
        assert pos.status == "OPEN"
        assert pos.entry_price == pytest.approx(0.505)  # midpoint + 0.005
        storage.save_trade.assert_called_once()
        storage.save_position.assert_called_once()

    def test_buy_rejected_returns_none(self):
        clob, storage = _mock_deps(midpoint=0.50)
        clob.place_limit_order.return_value = {"orderID": "ord_2", "status": "REJECTED"}
        engine = LiveEngine(clob, storage)

        with patch.object(type(engine), "bankroll", new_callable=lambda: property(lambda self: 1000.0)):
            pos = engine.execute_buy(_make_signal())

        assert pos is None
        # rejected trade is still recorded
        trade_arg = storage.save_trade.call_args[0][0]
        assert trade_arg.status == "REJECTED"

    def test_buy_returns_none_when_bankroll_low(self):
        clob, storage = _mock_deps()
        engine = LiveEngine(clob, storage)

        with patch.object(type(engine), "bankroll", new_callable=lambda: property(lambda self: 0.50)):
            pos = engine.execute_buy(_make_signal())

        assert pos is None
        clob.place_limit_order.assert_not_called()

    def test_buy_returns_none_when_no_midpoint(self):
        clob, storage = _mock_deps(midpoint=0)
        engine = LiveEngine(clob, storage)

        with patch.object(type(engine), "bankroll", new_callable=lambda: property(lambda self: 1000.0)):
            pos = engine.execute_buy(_make_signal())

        assert pos is None

    def test_buy_exception_returns_none(self):
        clob, storage = _mock_deps(midpoint=0.50)
        clob.place_limit_order.side_effect = Exception("API down")
        engine = LiveEngine(clob, storage)

        with patch.object(type(engine), "bankroll", new_callable=lambda: property(lambda self: 1000.0)):
            pos = engine.execute_buy(_make_signal())

        assert pos is None


class TestLiveEngineSell:

    def test_sell_closes_position(self):
        clob, storage = _mock_deps(sell_price=0.65)
        clob.place_market_order.return_value = {"orderID": "ord_sell_1"}
        engine = LiveEngine(clob, storage)
        pos = _make_open_position(entry_price=0.50, size=100)
        pos.is_paper = False

        pnl = engine.execute_sell(pos, reason="leader_exit")

        assert pos.status == "CLOSED"
        assert pos.close_reason == "leader_exit"
        assert pnl == pytest.approx(15.0)
        storage.save_position.assert_called_once()
        storage.save_trade.assert_called_once()

    def test_sell_exception_returns_zero(self):
        clob, storage = _mock_deps()
        clob.get_price.side_effect = Exception("Network error")
        engine = LiveEngine(clob, storage)
        pos = _make_open_position()

        pnl = engine.execute_sell(pos)

        assert pnl == 0.0
