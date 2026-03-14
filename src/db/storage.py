"""
Polytrader Clone — SQLite Storage Layer
Persists leaders, trades, positions, and paper trades.
"""
import sqlite3
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path

from src import config
from src.models import Leader, Position, TradeRecord

log = logging.getLogger(__name__)


class Storage:
    """SQLite database for all persistent state."""

    def __init__(self, db_path: Path = None):
        self.db_path = db_path or config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        c = self.conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS leaders (
                wallet TEXT PRIMARY KEY,
                name TEXT DEFAULT '',
                win_rate REAL DEFAULT 0,
                volume_usd REAL DEFAULT 0,
                pnl_usd REAL DEFAULT 0,
                total_trades INTEGER DEFAULT 0,
                crypto_ratio REAL DEFAULT 0,
                last_scanned TEXT,
                active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_slug TEXT,
                token_id TEXT,
                side TEXT,
                entry_price REAL,
                size REAL,
                cost_usd REAL,
                current_price REAL DEFAULT 0,
                high_price REAL DEFAULT 0,
                pnl_usd REAL DEFAULT 0,
                leader_wallet TEXT,
                opened_at TEXT,
                closed_at TEXT,
                close_reason TEXT DEFAULT '',
                is_paper INTEGER DEFAULT 1,
                status TEXT DEFAULT 'OPEN'
            );

            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market_slug TEXT,
                token_id TEXT,
                side TEXT,
                price REAL,
                size REAL,
                cost_usd REAL,
                leader_wallet TEXT,
                is_paper INTEGER DEFAULT 1,
                timestamp TEXT,
                order_id TEXT DEFAULT '',
                status TEXT DEFAULT 'FILLED',
                guard_blocked TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS leader_last_seen (
                wallet TEXT PRIMARY KEY,
                last_trade_ts INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
            CREATE INDEX IF NOT EXISTS idx_trades_ts ON trades(timestamp);
        """)
        self.conn.commit()

    # ── Leaders ───────────────────────────────────────────

    def save_leader(self, leader: Leader):
        self.conn.execute("""
            INSERT OR REPLACE INTO leaders
            (wallet, name, win_rate, volume_usd, pnl_usd, total_trades,
             crypto_ratio, last_scanned, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            leader.wallet, leader.name, leader.win_rate, leader.volume_usd,
            leader.pnl_usd, leader.total_trades, leader.crypto_ratio,
            leader.last_scanned.isoformat(), int(leader.active),
        ))
        self.conn.commit()

    def get_active_leaders(self) -> list[Leader]:
        rows = self.conn.execute(
            "SELECT * FROM leaders WHERE active = 1"
        ).fetchall()
        return [self._row_to_leader(r) for r in rows]

    def deactivate_all_leaders(self):
        self.conn.execute("UPDATE leaders SET active = 0")
        self.conn.commit()

    def _row_to_leader(self, row) -> Leader:
        return Leader(
            wallet=row["wallet"],
            name=row["name"],
            win_rate=row["win_rate"],
            volume_usd=row["volume_usd"],
            pnl_usd=row["pnl_usd"],
            total_trades=row["total_trades"],
            crypto_ratio=row["crypto_ratio"],
            last_scanned=datetime.fromisoformat(row["last_scanned"]),
            active=bool(row["active"]),
        )

    # ── Positions ─────────────────────────────────────────

    def save_position(self, pos: Position) -> int:
        if pos.id:
            self.conn.execute("""
                UPDATE positions SET current_price=?, high_price=?, pnl_usd=?,
                closed_at=?, close_reason=?, status=? WHERE id=?
            """, (pos.current_price, pos.high_price, pos.pnl_usd,
                  pos.closed_at.isoformat() if pos.closed_at else None,
                  pos.close_reason, pos.status, pos.id))
        else:
            cur = self.conn.execute("""
                INSERT INTO positions
                (market_slug, token_id, side, entry_price, size, cost_usd,
                 current_price, high_price, leader_wallet, opened_at, is_paper, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (pos.market_slug, pos.token_id, pos.side, pos.entry_price,
                  pos.size, pos.cost_usd, pos.current_price, pos.high_price,
                  pos.leader_wallet, pos.opened_at.isoformat(),
                  int(pos.is_paper), pos.status))
            pos.id = cur.lastrowid
        self.conn.commit()
        return pos.id

    def get_open_positions(self, is_paper: bool = True) -> list[Position]:
        rows = self.conn.execute(
            "SELECT * FROM positions WHERE status = 'OPEN' AND is_paper = ?",
            (int(is_paper),)
        ).fetchall()
        return [self._row_to_position(r) for r in rows]

    def get_all_positions(self, limit: int = 100) -> list[Position]:
        rows = self.conn.execute(
            "SELECT * FROM positions ORDER BY opened_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._row_to_position(r) for r in rows]

    def _row_to_position(self, row) -> Position:
        return Position(
            id=row["id"],
            market_slug=row["market_slug"],
            token_id=row["token_id"],
            side=row["side"],
            entry_price=row["entry_price"],
            size=row["size"],
            cost_usd=row["cost_usd"],
            current_price=row["current_price"],
            high_price=row["high_price"],
            pnl_usd=row["pnl_usd"],
            leader_wallet=row["leader_wallet"],
            opened_at=datetime.fromisoformat(row["opened_at"]),
            closed_at=datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
            close_reason=row["close_reason"],
            is_paper=bool(row["is_paper"]),
            status=row["status"],
        )

    # ── Trades ────────────────────────────────────────────

    def save_trade(self, trade: TradeRecord) -> int:
        cur = self.conn.execute("""
            INSERT INTO trades
            (market_slug, token_id, side, price, size, cost_usd,
             leader_wallet, is_paper, timestamp, order_id, status, guard_blocked)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (trade.market_slug, trade.token_id, trade.side, trade.price,
              trade.size, trade.cost_usd, trade.leader_wallet,
              int(trade.is_paper), trade.timestamp.isoformat(),
              trade.order_id, trade.status, trade.guard_blocked))
        trade.id = cur.lastrowid
        self.conn.commit()
        return trade.id

    def get_recent_trades(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Last seen timestamps for polling ──────────────────

    def get_last_seen_ts(self, wallet: str) -> int:
        row = self.conn.execute(
            "SELECT last_trade_ts FROM leader_last_seen WHERE wallet = ?",
            (wallet,)
        ).fetchone()
        return row["last_trade_ts"] if row else 0

    def set_last_seen_ts(self, wallet: str, ts: int):
        self.conn.execute("""
            INSERT OR REPLACE INTO leader_last_seen (wallet, last_trade_ts)
            VALUES (?, ?)
        """, (wallet, ts))
        self.conn.commit()

    # ── Stats ─────────────────────────────────────────────

    def get_pnl_summary(self, is_paper: bool = True) -> dict:
        row = self.conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN pnl_usd > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN pnl_usd < 0 THEN 1 ELSE 0 END) as losses,
                SUM(pnl_usd) as total_pnl,
                AVG(pnl_usd) as avg_pnl
            FROM positions WHERE status = 'CLOSED' AND is_paper = ?
        """, (int(is_paper),)).fetchone()
        return dict(row) if row else {}

    def close(self):
        self.conn.close()
