"""
Unit tests for the SQLite Storage layer.
Uses an in-memory database for speed.
Run with: pytest tests/test_storage.py
"""
import pytest
from pathlib import Path
from datetime import datetime, timezone, timedelta

from src.models import Leader, Position, TradeRecord
from src.db.storage import Storage


@pytest.fixture
def db(tmp_path):
    """Fresh in-memory-like SQLite database per test."""
    return Storage(db_path=tmp_path / "test.db")


# ── Leaders ──────────────────────────────────────────────

class TestLeaders:

    def test_save_and_get_leader(self, db):
        leader = Leader(
            wallet="0xABC",
            name="Alice",
            win_rate=72.5,
            volume_usd=50000,
            pnl_usd=3000,
            total_trades=120,
            crypto_ratio=0.15,
            last_scanned=datetime.now(timezone.utc),
            active=True,
        )
        db.save_leader(leader)

        leaders = db.get_active_leaders()
        assert len(leaders) == 1
        assert leaders[0].wallet == "0xABC"
        assert leaders[0].name == "Alice"
        assert leaders[0].win_rate == 72.5

    def test_deactivate_all_leaders(self, db):
        for w in ["0x1", "0x2", "0x3"]:
            db.save_leader(Leader(
                wallet=w, name=w,
                last_scanned=datetime.now(timezone.utc),
                active=True,
            ))

        db.deactivate_all_leaders()
        assert len(db.get_active_leaders()) == 0

    def test_upsert_leader(self, db):
        leader = Leader(wallet="0xABC", name="Alice",
                        last_scanned=datetime.now(timezone.utc), active=True)
        db.save_leader(leader)

        leader.win_rate = 80.0
        leader.name = "Alice Updated"
        db.save_leader(leader)

        leaders = db.get_active_leaders()
        assert len(leaders) == 1
        assert leaders[0].win_rate == 80.0
        assert leaders[0].name == "Alice Updated"


# ── Positions ────────────────────────────────────────────

class TestPositions:

    def test_save_new_position(self, db):
        pos = Position(
            market_slug="test-market",
            token_id="tok1",
            side="BUY",
            entry_price=0.50,
            size=100,
            cost_usd=50.0,
            current_price=0.50,
            high_price=0.50,
            leader_wallet="0xA",
            opened_at=datetime.now(timezone.utc),
            is_paper=True,
            status="OPEN",
        )
        pos_id = db.save_position(pos)

        assert pos_id is not None
        assert pos.id == pos_id

    def test_get_open_positions(self, db):
        for i in range(3):
            pos = Position(
                market_slug=f"market-{i}",
                token_id=f"tok{i}",
                side="BUY",
                entry_price=0.50,
                size=100,
                cost_usd=50.0,
                current_price=0.50,
                high_price=0.50,
                leader_wallet="0xA",
                opened_at=datetime.now(timezone.utc),
                is_paper=True,
                status="OPEN" if i < 2 else "CLOSED",
            )
            db.save_position(pos)

        open_pos = db.get_open_positions(is_paper=True)
        assert len(open_pos) == 2

    def test_update_position(self, db):
        pos = Position(
            market_slug="test-market",
            token_id="tok1",
            side="BUY",
            entry_price=0.50,
            size=100,
            cost_usd=50.0,
            current_price=0.50,
            high_price=0.50,
            leader_wallet="0xA",
            opened_at=datetime.now(timezone.utc),
            is_paper=True,
            status="OPEN",
        )
        db.save_position(pos)

        pos.current_price = 0.65
        pos.high_price = 0.65
        pos.pnl_usd = 15.0
        pos.status = "CLOSED"
        pos.close_reason = "trailing_stop"
        pos.closed_at = datetime.now(timezone.utc)
        db.save_position(pos)

        all_pos = db.get_all_positions()
        assert len(all_pos) == 1
        assert all_pos[0].status == "CLOSED"
        assert all_pos[0].pnl_usd == 15.0
        assert all_pos[0].close_reason == "trailing_stop"

    def test_paper_vs_live_isolation(self, db):
        for is_paper in [True, False]:
            pos = Position(
                market_slug="market",
                token_id="tok1",
                side="BUY",
                entry_price=0.50,
                size=100,
                cost_usd=50.0,
                current_price=0.50,
                high_price=0.50,
                leader_wallet="0xA",
                opened_at=datetime.now(timezone.utc),
                is_paper=is_paper,
                status="OPEN",
            )
            db.save_position(pos)

        assert len(db.get_open_positions(is_paper=True)) == 1
        assert len(db.get_open_positions(is_paper=False)) == 1


# ── Trades ───────────────────────────────────────────────

class TestTrades:

    def test_save_and_get_trade(self, db):
        trade = TradeRecord(
            market_slug="test-market",
            token_id="tok1",
            side="BUY",
            price=0.50,
            size=100,
            cost_usd=50.0,
            leader_wallet="0xA",
            is_paper=True,
            timestamp=datetime.now(timezone.utc),
            status="FILLED",
        )
        trade_id = db.save_trade(trade)

        assert trade_id is not None
        recent = db.get_recent_trades(limit=10)
        assert len(recent) == 1
        assert recent[0]["side"] == "BUY"
        assert recent[0]["price"] == 0.50


# ── Last Seen ────────────────────────────────────────────

class TestLastSeen:

    def test_default_zero(self, db):
        assert db.get_last_seen_ts("0xUnknown") == 0

    def test_set_and_get(self, db):
        db.set_last_seen_ts("0xA", 12345)
        assert db.get_last_seen_ts("0xA") == 12345

    def test_upsert(self, db):
        db.set_last_seen_ts("0xA", 100)
        db.set_last_seen_ts("0xA", 200)
        assert db.get_last_seen_ts("0xA") == 200


# ── PnL Summary ─────────────────────────────────────────

class TestPnlSummary:

    def test_summary_with_closed_positions(self, db):
        for pnl in [10.0, -5.0, 20.0, -3.0]:
            # First insert as OPEN (INSERT path doesn't include pnl_usd)
            pos = Position(
                market_slug="m",
                token_id="t",
                side="BUY",
                entry_price=0.50,
                size=100,
                cost_usd=50.0,
                current_price=0.50,
                high_price=0.50,
                leader_wallet="0xA",
                opened_at=datetime.now(timezone.utc),
                is_paper=True,
                status="OPEN",
            )
            db.save_position(pos)
            # Then close with pnl (UPDATE path)
            pos.pnl_usd = pnl
            pos.status = "CLOSED"
            pos.close_reason = "test"
            pos.closed_at = datetime.now(timezone.utc)
            db.save_position(pos)

        summary = db.get_pnl_summary(is_paper=True)
        assert summary["total"] == 4
        assert summary["wins"] == 2
        assert summary["losses"] == 2
        assert summary["total_pnl"] == pytest.approx(22.0)

    def test_summary_ignores_open_positions(self, db):
        pos = Position(
            market_slug="m",
            token_id="t",
            side="BUY",
            entry_price=0.50,
            size=100,
            cost_usd=50.0,
            pnl_usd=10.0,
            leader_wallet="0xA",
            opened_at=datetime.now(timezone.utc),
            is_paper=True,
            status="OPEN",
        )
        db.save_position(pos)

        summary = db.get_pnl_summary(is_paper=True)
        assert summary["total"] == 0
