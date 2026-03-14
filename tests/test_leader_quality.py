"""
Unit tests for the Leader Quality guard.
Run with: pytest tests/test_leader_quality.py
"""
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone, timedelta

from src.models import TradeSignal, Leader, Market, Position
from src.guards.leader_quality import check_leader_quality


# ── Helpers ──────────────────────────────────────────────

def _make_signal(
    win_rate=70.0,
    active=True,
    last_scanned=None,
    token_id="tok1",
    wallet="0xLeader",
):
    leader = Leader(
        wallet=wallet,
        name="TestLeader",
        win_rate=win_rate,
        volume_usd=50000,
        active=active,
        last_scanned=last_scanned or datetime.now(timezone.utc),
    )
    market = Market(condition_id="c1", token_id=token_id, question="Test?")
    return TradeSignal(leader=leader, market=market, side="BUY", token_id=token_id)


def _mock_storage(open_positions=None):
    storage = MagicMock()
    storage.get_open_positions.return_value = open_positions or []
    return storage


# ── Tests ────────────────────────────────────────────────

class TestLeaderQuality:

    def test_passes_valid_leader(self):
        sig = _make_signal(win_rate=70)
        result = check_leader_quality(sig, _mock_storage())
        assert result == ""

    def test_blocks_inactive_leader(self):
        sig = _make_signal(active=False)
        result = check_leader_quality(sig, _mock_storage())
        assert result == "leader_inactive"

    def test_blocks_low_win_rate(self):
        sig = _make_signal(win_rate=40)
        result = check_leader_quality(sig, _mock_storage())
        assert "leader_low_wr" in result

    def test_allows_exact_min_win_rate(self):
        sig = _make_signal(win_rate=55.0)  # == MIN_WIN_RATE
        result = check_leader_quality(sig, _mock_storage())
        assert result == ""

    def test_blocks_duplicate_position(self):
        existing = Position(
            token_id="tok1",
            leader_wallet="0xLeader",
            status="OPEN",
        )
        sig = _make_signal(token_id="tok1", wallet="0xLeader")
        result = check_leader_quality(sig, _mock_storage([existing]))
        assert result == "already_in_position"

    def test_allows_different_token(self):
        existing = Position(
            token_id="tok_other",
            leader_wallet="0xLeader",
            status="OPEN",
        )
        sig = _make_signal(token_id="tok1", wallet="0xLeader")
        result = check_leader_quality(sig, _mock_storage([existing]))
        assert result == ""

    def test_allows_same_token_different_leader(self):
        existing = Position(
            token_id="tok1",
            leader_wallet="0xOtherLeader",
            status="OPEN",
        )
        sig = _make_signal(token_id="tok1", wallet="0xLeader")
        result = check_leader_quality(sig, _mock_storage([existing]))
        assert result == ""

    def test_stale_scan_warns_but_passes(self):
        """Stale scan data should NOT block, only warn."""
        stale_time = datetime.now(timezone.utc) - timedelta(hours=72)
        sig = _make_signal(last_scanned=stale_time)
        result = check_leader_quality(sig, _mock_storage())
        assert result == ""
