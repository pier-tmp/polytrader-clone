"""
Unit tests for PortfolioManager.
Run with: pytest tests/test_portfolio_manager.py
"""
import pytest
from unittest.mock import MagicMock, patch

from src.models import Position, Market, TradeSignal
from src.portfolio.manager import PortfolioManager


# ── Helpers ──────────────────────────────────────────────

def _make_position(entry_price=0.50, size=100.0, high_price=None, token_id="tok1"):
    return Position(
        id=1,
        market_slug="some-market",
        token_id=token_id,
        side="BUY",
        entry_price=entry_price,
        size=size,
        cost_usd=entry_price * size,
        current_price=entry_price,
        high_price=high_price or entry_price,
        leader_wallet="0xLeader",
        is_paper=True,
        status="OPEN",
    )


def _mock_deps():
    clob = MagicMock()
    storage = MagicMock()
    engine = MagicMock()
    engine.execute_sell.return_value = 0.0
    storage.get_open_positions.return_value = []
    storage.get_pnl_summary.return_value = {"total_pnl": 0, "total": 0, "wins": 0, "losses": 0}
    return clob, storage, engine


# ── Update Cycle ─────────────────────────────────────────

class TestUpdateCycle:

    def test_no_positions_does_nothing(self):
        clob, storage, engine = _mock_deps()
        mgr = PortfolioManager(clob, storage, engine)

        mgr.update_cycle()

        engine.execute_sell.assert_not_called()
        storage.save_position.assert_not_called()

    def test_updates_price_and_saves(self):
        clob, storage, engine = _mock_deps()
        pos = _make_position(entry_price=0.40, size=100)
        storage.get_open_positions.return_value = [pos]
        clob.get_price.return_value = 0.45
        mgr = PortfolioManager(clob, storage, engine)

        mgr.update_cycle()

        assert pos.current_price == 0.45
        assert pos.pnl_usd == pytest.approx(5.0)
        storage.save_position.assert_called_once_with(pos)

    def test_skips_when_price_zero(self):
        clob, storage, engine = _mock_deps()
        pos = _make_position()
        storage.get_open_positions.return_value = [pos]
        clob.get_price.return_value = 0
        clob.get_midpoint.return_value = 0
        mgr = PortfolioManager(clob, storage, engine)

        mgr.update_cycle()

        storage.save_position.assert_not_called()
        engine.execute_sell.assert_not_called()


# ── Cashout ──────────────────────────────────────────────

class TestCashout:

    def test_cashout_at_threshold(self):
        clob, storage, engine = _mock_deps()
        pos = _make_position(entry_price=0.50, size=100)
        storage.get_open_positions.return_value = [pos]
        clob.get_price.return_value = 0.98  # == CASHOUT_THRESHOLD
        engine.execute_sell.return_value = 48.0
        mgr = PortfolioManager(clob, storage, engine)

        mgr.update_cycle()

        engine.execute_sell.assert_called_once_with(pos, "cashout")

    def test_no_cashout_below_threshold(self):
        clob, storage, engine = _mock_deps()
        pos = _make_position(entry_price=0.50, size=100)
        storage.get_open_positions.return_value = [pos]
        clob.get_price.return_value = 0.90
        mgr = PortfolioManager(clob, storage, engine)

        mgr.update_cycle()

        engine.execute_sell.assert_not_called()


# ── Trailing Stop ────────────────────────────────────────

class TestTrailingStop:

    def test_trailing_stop_triggers(self):
        """15% drop from high should trigger trailing stop."""
        clob, storage, engine = _mock_deps()
        # high_price=0.80, current drops to 0.65 → drop = 18.75% > 15%
        pos = _make_position(entry_price=0.50, size=100, high_price=0.80)
        storage.get_open_positions.return_value = [pos]
        clob.get_price.return_value = 0.65
        engine.execute_sell.return_value = 15.0
        mgr = PortfolioManager(clob, storage, engine)

        mgr.update_cycle()

        engine.execute_sell.assert_called_once_with(pos, "trailing_stop")

    def test_trailing_stop_no_trigger_small_drop(self):
        """5% drop should not trigger (threshold is 15%)."""
        clob, storage, engine = _mock_deps()
        pos = _make_position(entry_price=0.50, size=100, high_price=0.80)
        storage.get_open_positions.return_value = [pos]
        clob.get_price.return_value = 0.76  # 5% drop from 0.80
        mgr = PortfolioManager(clob, storage, engine)

        mgr.update_cycle()

        engine.execute_sell.assert_not_called()

    def test_trailing_stop_only_when_in_profit(self):
        """Trailing stop should not trigger when high == entry (no profit yet)."""
        clob, storage, engine = _mock_deps()
        pos = _make_position(entry_price=0.50, size=100, high_price=0.50)
        storage.get_open_positions.return_value = [pos]
        clob.get_price.return_value = 0.40  # 20% drop, but high == entry
        mgr = PortfolioManager(clob, storage, engine)

        mgr.update_cycle()

        engine.execute_sell.assert_not_called()

    @patch("src.portfolio.manager.is_sports_trailing_stop_exempt", return_value=True)
    def test_sports_exempt_from_trailing_stop(self, mock_exempt):
        """Sports markets should skip trailing stop even if drop > threshold."""
        clob, storage, engine = _mock_deps()
        pos = _make_position(entry_price=0.50, size=100, high_price=0.80)
        storage.get_open_positions.return_value = [pos]
        clob.get_price.return_value = 0.60  # 25% drop
        mgr = PortfolioManager(clob, storage, engine)

        mgr.update_cycle()

        engine.execute_sell.assert_not_called()


# ── Close Position Without Engine ────────────────────────

class TestCloseWithoutEngine:

    def test_fallback_closes_in_db(self):
        clob, storage, _ = _mock_deps()
        pos = _make_position(entry_price=0.50, size=100)
        pos.current_price = 0.60
        storage.get_open_positions.return_value = [pos]
        clob.get_price.return_value = 0.99  # triggers cashout
        mgr = PortfolioManager(clob, storage, engine=None)

        mgr.update_cycle()

        assert pos.status == "CLOSED"
        assert pos.close_reason == "cashout"
        assert pos.closed_at is not None
        storage.save_position.assert_called()


# ── Portfolio Summary ────────────────────────────────────

class TestPortfolioSummary:

    def test_summary_with_positions(self):
        clob, storage, engine = _mock_deps()
        pos1 = _make_position(entry_price=0.40, size=100)
        pos1.pnl_usd = 10.0
        pos2 = _make_position(entry_price=0.60, size=50)
        pos2.pnl_usd = -5.0
        storage.get_open_positions.return_value = [pos1, pos2]
        storage.get_pnl_summary.return_value = {
            "total_pnl": 25.0, "total": 10, "wins": 7, "losses": 3,
        }
        mgr = PortfolioManager(clob, storage, engine)

        summary = mgr.get_portfolio_summary()

        assert summary["open_positions"] == 2
        assert summary["unrealized_pnl"] == 5.0
        assert summary["realized_pnl"] == 25.0
        assert summary["total_pnl"] == 30.0
        assert summary["win_rate"] == 70.0

    def test_summary_empty_portfolio(self):
        clob, storage, engine = _mock_deps()
        mgr = PortfolioManager(clob, storage, engine)

        summary = mgr.get_portfolio_summary()

        assert summary["open_positions"] == 0
        assert summary["unrealized_pnl"] == 0
        assert summary["total_pnl"] == 0
