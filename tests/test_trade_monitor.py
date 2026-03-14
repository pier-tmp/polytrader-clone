"""
Unit tests for TradeMonitor.
Run with: pytest tests/test_trade_monitor.py
"""
import pytest
from unittest.mock import MagicMock, call

from src.models import Leader
from src.scanner.trade_monitor import TradeMonitor


# ── Helpers ──────────────────────────────────────────────

def _make_leader(wallet="0xAlice", name="Alice"):
    return Leader(wallet=wallet, name=name, win_rate=70, volume_usd=50000)


def _mock_deps():
    data = MagicMock()
    gamma = MagicMock()
    storage = MagicMock()
    return data, gamma, storage


# ── Poll Cycle ───────────────────────────────────────────

class TestPollCycle:

    def test_no_leaders_skips(self):
        data, gamma, storage = _mock_deps()
        storage.get_active_leaders.return_value = []
        monitor = TradeMonitor(data, gamma, storage)

        monitor._poll_cycle()

        data.get_recent_trades.assert_not_called()

    def test_no_new_trades(self):
        data, gamma, storage = _mock_deps()
        leader = _make_leader()
        storage.get_active_leaders.return_value = [leader]
        storage.get_last_seen_ts.return_value = 1000
        data.get_recent_trades.return_value = []
        callback = MagicMock()
        monitor = TradeMonitor(data, gamma, storage, on_signal=callback)

        monitor._poll_cycle()

        callback.assert_not_called()

    def test_emits_signal_for_new_trade(self):
        data, gamma, storage = _mock_deps()
        leader = _make_leader()
        storage.get_active_leaders.return_value = [leader]
        storage.get_last_seen_ts.return_value = 1000
        data.get_recent_trades.return_value = [
            {
                "timestamp": 1500,
                "conditionId": "cond1",
                "side": "BUY",
                "usdcSize": "25.00",
                "price": "0.50",
                "asset": "tok1",
                "slug": "test-market",
                "title": "Test Market?",
            }
        ]
        gamma.get_market.return_value = {
            "question": "Test Market?",
            "slug": "test-market",
            "tags": ["politics"],
            "volume24hr": 100000,
            "liquidity": 200000,
        }
        callback = MagicMock()
        monitor = TradeMonitor(data, gamma, storage, on_signal=callback)

        monitor._poll_cycle()

        callback.assert_called_once()
        sig = callback.call_args[0][0]
        assert sig.side == "BUY"
        assert sig.token_id == "tok1"
        assert sig.leader.wallet == "0xAlice"

    def test_updates_last_seen_ts(self):
        data, gamma, storage = _mock_deps()
        leader = _make_leader()
        storage.get_active_leaders.return_value = [leader]
        storage.get_last_seen_ts.return_value = 1000
        data.get_recent_trades.return_value = [
            {"timestamp": 2000, "conditionId": "", "side": "BUY",
             "price": "0.5", "asset": "t1"},
            {"timestamp": 2500, "conditionId": "", "side": "SELL",
             "price": "0.6", "asset": "t1"},
        ]
        gamma.get_market.return_value = {}
        monitor = TradeMonitor(data, gamma, storage, on_signal=MagicMock())

        monitor._poll_cycle()

        storage.set_last_seen_ts.assert_called_once_with("0xAlice", 2500)

    def test_skips_old_trades(self):
        data, gamma, storage = _mock_deps()
        leader = _make_leader()
        storage.get_active_leaders.return_value = [leader]
        storage.get_last_seen_ts.return_value = 5000
        data.get_recent_trades.return_value = [
            {"timestamp": 4000, "conditionId": "", "side": "BUY",
             "price": "0.5", "asset": "t1"},
        ]
        callback = MagicMock()
        monitor = TradeMonitor(data, gamma, storage, on_signal=callback)

        monitor._poll_cycle()

        callback.assert_not_called()


# ── Build Signal ─────────────────────────────────────────

class TestBuildSignal:

    def test_builds_signal_with_market_data(self):
        data, gamma, storage = _mock_deps()
        leader = _make_leader()
        gamma.get_market.return_value = {
            "question": "Will X win?",
            "slug": "will-x-win",
            "tags": [{"slug": "politics"}, {"slug": "usa"}],
            "volume24hr": 50000,
            "liquidity": 100000,
            "endDate": "2026-06-01T00:00:00Z",
        }
        monitor = TradeMonitor(data, gamma, storage)

        trade = {
            "conditionId": "cond1",
            "side": "buy",
            "usdcSize": "100.00",
            "price": "0.65",
            "asset": "tok_xyz",
            "slug": "will-x-win",
            "title": "Will X win?",
            "timestamp": 1700000000,
        }
        sig = monitor._build_signal(leader, trade)

        assert sig is not None
        assert sig.side == "BUY"
        assert sig.size_usd == 100.0
        assert sig.price == 0.65
        assert sig.market.question == "Will X win?"
        assert sig.market.tags == ["politics", "usa"]
        assert sig.market.end_date is not None

    def test_build_signal_handles_missing_data(self):
        data, gamma, storage = _mock_deps()
        leader = _make_leader()
        gamma.get_market.return_value = {}
        monitor = TradeMonitor(data, gamma, storage)

        trade = {
            "conditionId": "cond1",
            "side": "SELL",
            "price": "0.30",
            "asset": "tok1",
            "timestamp": 0,
        }
        sig = monitor._build_signal(leader, trade)

        assert sig is not None
        assert sig.side == "SELL"

    def test_build_signal_returns_none_on_exception(self):
        data, gamma, storage = _mock_deps()
        leader = _make_leader()
        gamma.get_market.side_effect = Exception("API fail")
        monitor = TradeMonitor(data, gamma, storage)

        sig = monitor._build_signal(leader, {"conditionId": "x"})

        assert sig is None


# ── Start/Stop ───────────────────────────────────────────

class TestStartStop:

    def test_stop_sets_flag(self):
        data, gamma, storage = _mock_deps()
        monitor = TradeMonitor(data, gamma, storage)

        monitor.stop()

        assert monitor._running is False
