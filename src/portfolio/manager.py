"""
Portfolio Manager — Monitors open positions and manages exits.
Handles: trailing stop-loss, instant CLOB cashout, price updates.
"""
import logging
from datetime import datetime, timezone

from src import config
from src.models import Position
from src.api.clob_client import ClobClient
from src.db.storage import Storage
from src.guards.sports_aware import is_sports_trailing_stop_exempt
from src.models import TradeSignal, Market

log = logging.getLogger(__name__)


class PortfolioManager:
    """
    Runs periodically to:
    1. Update current prices for all open positions
    2. Check trailing stop-loss triggers
    3. Check instant cashout triggers (price >= 0.98)
    4. Compute P&L
    """

    def __init__(self, clob: ClobClient, storage: Storage, engine=None):
        self.clob = clob
        self.db = storage
        self.engine = engine  # Paper or Live engine for executing sells
        self.is_paper = config.TRADING_MODE == "paper"

    def update_cycle(self):
        """Run a full update cycle on all open positions."""
        positions = self.db.get_open_positions(is_paper=self.is_paper)
        if not positions:
            return

        closed_count = 0
        total_pnl = 0.0

        for pos in positions:
            # Update price
            current_price = self.clob.get_price(pos.token_id, "SELL")
            if current_price <= 0:
                current_price = self.clob.get_midpoint(pos.token_id)
            if current_price <= 0:
                continue

            pos.update_pnl(current_price)

            # Check cashout (price near $1.00 — market almost resolved)
            if current_price >= config.CASHOUT_THRESHOLD:
                pnl = self._close_position(pos, "cashout")
                closed_count += 1
                total_pnl += pnl
                continue

            # Check trailing stop-loss (skip for sports markets)
            if not self._is_sports_exempt(pos):
                drop_from_high = (pos.high_price - current_price) / pos.high_price * 100
                if drop_from_high >= config.TRAILING_STOP_PERCENT and pos.high_price > pos.entry_price:
                    pnl = self._close_position(pos, "trailing_stop")
                    closed_count += 1
                    total_pnl += pnl
                    continue

            # Save updated price
            self.db.save_position(pos)

        if closed_count:
            log.info(
                "Portfolio update: %d positions closed, net P&L: $%.2f",
                closed_count, total_pnl,
            )

    def _close_position(self, pos: Position, reason: str) -> float:
        """Close a position via the engine."""
        if self.engine:
            return self.engine.execute_sell(pos, reason)
        else:
            # Fallback: just update the DB
            current_price = pos.current_price
            pos.update_pnl(current_price)
            pos.closed_at = datetime.now(timezone.utc)
            pos.close_reason = reason
            pos.status = "CLOSED"
            self.db.save_position(pos)
            return pos.pnl_usd

    def _is_sports_exempt(self, pos: Position) -> bool:
        """Check if position is in a sports market (exempt from trailing stop)."""
        # Build a minimal signal to check
        dummy_market = Market(
            condition_id="",
            token_id=pos.token_id,
            slug=pos.market_slug,
            tags=[],
        )
        dummy_signal = TradeSignal(
            leader=None,
            market=dummy_market,
            side=pos.side,
        )
        return is_sports_trailing_stop_exempt(dummy_signal)

    def get_portfolio_summary(self) -> dict:
        """Get a summary of the current portfolio state."""
        open_pos = self.db.get_open_positions(is_paper=self.is_paper)
        pnl_summary = self.db.get_pnl_summary(is_paper=self.is_paper)

        unrealized_pnl = sum(p.pnl_usd for p in open_pos)
        invested = sum(p.cost_usd for p in open_pos)
        realized = pnl_summary.get("total_pnl", 0) or 0

        return {
            "mode": config.TRADING_MODE,
            "bankroll_initial": config.PAPER_BANKROLL if self.is_paper else config.LIVE_BANKROLL,
            "invested": round(invested, 2),
            "open_positions": len(open_pos),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "realized_pnl": round(realized, 2),
            "total_pnl": round(realized + unrealized_pnl, 2),
            "total_trades": pnl_summary.get("total", 0),
            "wins": pnl_summary.get("wins", 0),
            "losses": pnl_summary.get("losses", 0),
            "win_rate": round(
                (pnl_summary.get("wins", 0) / max(pnl_summary.get("total", 1), 1)) * 100, 1
            ),
        }
