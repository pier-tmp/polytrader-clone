"""
Unit tests for TelegramNotifier.
Run with: pytest tests/test_telegram.py
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

from src.models import Position, TradeSignal, Leader, Market
from src.notifications.telegram_bot import TelegramNotifier


# ── Helpers ──────────────────────────────────────────────

def _make_notifier(enabled=True):
    with patch("src.notifications.telegram_bot.config") as mock_cfg:
        mock_cfg.TELEGRAM_BOT_TOKEN = "fake_token" if enabled else ""
        mock_cfg.TELEGRAM_CHAT_ID = "12345" if enabled else ""
        notifier = TelegramNotifier()
    # Override after init so _send works
    notifier.token = "fake_token" if enabled else ""
    notifier.chat_id = "12345" if enabled else ""
    notifier.enabled = enabled
    return notifier


def _make_signal():
    leader = Leader(wallet="0xLeader", name="Alice", win_rate=70, volume_usd=50000)
    market = Market(condition_id="c1", token_id="t1", question="Will X happen?",
                    slug="will-x-happen", tags=["politics"])
    return TradeSignal(leader=leader, market=market, side="BUY", token_id="t1")


def _make_position(pnl=10.0, reason="trailing_stop", is_paper=True):
    now = datetime.now(timezone.utc)
    return Position(
        id=1,
        market_slug="will-x-happen",
        token_id="t1",
        side="BUY",
        entry_price=0.50,
        size=100,
        cost_usd=50.0,
        current_price=0.60,
        high_price=0.60,
        pnl_usd=pnl,
        leader_wallet="0xLeader",
        opened_at=now - timedelta(hours=3),
        closed_at=now,
        close_reason=reason,
        is_paper=is_paper,
        status="CLOSED",
    )


# ── Disabled ─────────────────────────────────────────────

class TestDisabled:

    @patch("src.notifications.telegram_bot.requests.post")
    def test_does_not_send_when_disabled(self, mock_post):
        notifier = _make_notifier(enabled=False)

        notifier.notify_trade_copied(_make_signal(), _make_position())

        mock_post.assert_not_called()


# ── Trade Alerts ─────────────────────────────────────────

class TestTradeAlerts:

    @patch("src.notifications.telegram_bot.requests.post")
    def test_notify_trade_copied(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        notifier = _make_notifier()
        sig = _make_signal()
        pos = _make_position(is_paper=True)

        notifier.notify_trade_copied(sig, pos)

        mock_post.assert_called_once()
        body = mock_post.call_args[1]["json"]["text"]
        assert "COPY TRADE" in body
        assert "PAPER" in body
        assert "Will X happen?" in body

    @patch("src.notifications.telegram_bot.requests.post")
    def test_notify_trade_blocked(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        notifier = _make_notifier()

        notifier.notify_trade_blocked(_make_signal(), "coinflip")

        body = mock_post.call_args[1]["json"]["text"]
        assert "BLOCKED" in body
        assert "coinflip" in body


# ── Exit Alerts ──────────────────────────────────────────

class TestExitAlerts:

    @patch("src.notifications.telegram_bot.requests.post")
    def test_notify_position_closed_profit(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        notifier = _make_notifier()
        pos = _make_position(pnl=15.0, reason="cashout")

        notifier.notify_position_closed(pos)

        body = mock_post.call_args[1]["json"]["text"]
        assert "CLOSED" in body
        assert "+15.00" in body

    @patch("src.notifications.telegram_bot.requests.post")
    def test_notify_position_closed_loss(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        notifier = _make_notifier()
        pos = _make_position(pnl=-8.0, reason="trailing_stop")

        notifier.notify_position_closed(pos)

        body = mock_post.call_args[1]["json"]["text"]
        assert "-8.00" in body


# ── Summary ──────────────────────────────────────────────

class TestSummary:

    @patch("src.notifications.telegram_bot.requests.post")
    def test_daily_summary(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        notifier = _make_notifier()
        summary = {
            "mode": "paper",
            "open_positions": 3,
            "invested": 150.0,
            "unrealized_pnl": 12.0,
            "realized_pnl": 45.0,
            "total_pnl": 57.0,
            "total_trades": 20,
            "wins": 14,
            "losses": 6,
            "win_rate": 70.0,
        }

        notifier.notify_daily_summary(summary)

        body = mock_post.call_args[1]["json"]["text"]
        assert "DAILY SUMMARY" in body
        assert "PAPER" in body
        assert "+57.00" in body


# ── Error ────────────────────────────────────────────────

class TestError:

    @patch("src.notifications.telegram_bot.requests.post")
    def test_notify_error(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        notifier = _make_notifier()

        notifier.notify_error("Something broke")

        body = mock_post.call_args[1]["json"]["text"]
        assert "ERROR" in body
        assert "Something broke" in body

    @patch("src.notifications.telegram_bot.requests.post")
    def test_send_handles_exception(self, mock_post):
        mock_post.side_effect = Exception("Network down")
        notifier = _make_notifier()

        # Should not raise
        notifier.notify_error("test")


# ── Duration Helper ──────────────────────────────────────

class TestDuration:

    def test_duration_minutes(self):
        notifier = _make_notifier()
        now = datetime.now(timezone.utc)
        pos = _make_position()
        pos.opened_at = now - timedelta(minutes=30)
        pos.closed_at = now

        result = notifier._duration(pos)
        assert result == "30m"

    def test_duration_hours(self):
        notifier = _make_notifier()
        now = datetime.now(timezone.utc)
        pos = _make_position()
        pos.opened_at = now - timedelta(hours=5)
        pos.closed_at = now

        result = notifier._duration(pos)
        assert result == "5.0h"

    def test_duration_days(self):
        notifier = _make_notifier()
        now = datetime.now(timezone.utc)
        pos = _make_position()
        pos.opened_at = now - timedelta(days=3)
        pos.closed_at = now

        result = notifier._duration(pos)
        assert result == "3.0d"

    def test_duration_no_closed_at(self):
        notifier = _make_notifier()
        pos = _make_position()
        pos.closed_at = None

        result = notifier._duration(pos)
        assert result == "N/A"
