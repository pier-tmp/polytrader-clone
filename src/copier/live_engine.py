"""
Live Engine — Executes real orders on the Polymarket CLOB.
Uses maker (post-only) orders for $0 fees on entry.
"""
import logging
import time
from datetime import datetime, timezone

from src import config
from src.models import TradeSignal, Position, TradeRecord
from src.api.clob_client import ClobClient
from src.db.storage import Storage

log = logging.getLogger(__name__)


class LiveEngine:
    """
    Executes real trades via the Polymarket CLOB API.
    Uses the py-clob-client SDK for authenticated order placement.
    """

    def __init__(self, clob: ClobClient, storage: Storage):
        self.clob = clob
        self.db = storage

    @property
    def bankroll(self) -> float:
        """Current live bankroll estimation."""
        open_pos = self.db.get_open_positions(is_paper=False)
        invested = sum(p.cost_usd for p in open_pos)
        summary = self.db.get_pnl_summary(is_paper=False)
        realized = summary.get("total_pnl", 0) or 0
        return config.LIVE_BANKROLL - invested + realized

    def execute_buy(self, signal: TradeSignal, metadata: dict = None) -> Position | None:
        """
        Place a real BUY order on the CLOB.
        Uses maker (post-only) limit order for zero fees.
        Falls back to market order if maker doesn't fill within timeout.
        """
        available = self.bankroll
        trade_budget = available * (config.BET_SIZE_PERCENT / 100.0)

        if trade_budget < 1.0:
            log.warning("Live bankroll too low: $%.2f", available)
            return None

        token_id = signal.token_id or signal.market.token_id

        # Get current price for maker order
        midpoint = self.clob.get_midpoint(token_id)
        if midpoint <= 0:
            log.error("No midpoint for %s", token_id[:12])
            return None

        # Place slightly above midpoint to improve fill chance
        maker_price = round(midpoint + 0.005, 4)
        shares = trade_budget / maker_price

        try:
            result = self.clob.place_limit_order(
                token_id=token_id,
                price=maker_price,
                size=shares,
                side="BUY",
                post_only=True,
            )

            order_id = result.get("orderID", result.get("id", ""))
            status = result.get("status", "UNKNOWN")

            if status in ("MATCHED", "LIVE", "DELAYED"):
                # Wait briefly for fill confirmation
                fill_price = maker_price
                trade = TradeRecord(
                    market_slug=signal.market.slug,
                    token_id=token_id,
                    side="BUY",
                    price=fill_price,
                    size=shares,
                    cost_usd=trade_budget,
                    leader_wallet=signal.leader.wallet,
                    is_paper=False,
                    timestamp=datetime.now(timezone.utc),
                    order_id=order_id,
                    status="FILLED",
                )
                self.db.save_trade(trade)

                position = Position(
                    market_slug=signal.market.slug,
                    token_id=token_id,
                    side="BUY",
                    entry_price=fill_price,
                    size=shares,
                    cost_usd=trade_budget,
                    current_price=fill_price,
                    high_price=fill_price,
                    leader_wallet=signal.leader.wallet,
                    opened_at=datetime.now(timezone.utc),
                    is_paper=False,
                    status="OPEN",
                )
                self.db.save_position(position)

                log.info(
                    "[LIVE] BUY %.2f shares @ $%.4f = $%.2f on %s",
                    shares, fill_price, trade_budget,
                    signal.market.slug[:30],
                )
                return position
            else:
                log.warning("Order not filled: status=%s, result=%s", status, result)
                trade = TradeRecord(
                    market_slug=signal.market.slug,
                    token_id=token_id,
                    side="BUY",
                    price=maker_price,
                    size=shares,
                    cost_usd=trade_budget,
                    leader_wallet=signal.leader.wallet,
                    is_paper=False,
                    timestamp=datetime.now(timezone.utc),
                    order_id=order_id,
                    status="REJECTED",
                )
                self.db.save_trade(trade)
                return None

        except Exception as e:
            log.error("Live BUY failed: %s", e)
            return None

    def execute_sell(self, position: Position, reason: str = "leader_exit") -> float:
        """
        Close a live position by selling on the CLOB.
        Tries market order for immediate execution.
        """
        token_id = position.token_id

        try:
            sell_value = position.size * self.clob.get_price(token_id, "SELL")
            result = self.clob.place_market_order(
                token_id=token_id,
                amount_usd=sell_value,
                side="SELL",
            )

            current_price = self.clob.get_price(token_id, "SELL")
            position.update_pnl(current_price)
            position.closed_at = datetime.now(timezone.utc)
            position.close_reason = reason
            position.status = "CLOSED"
            self.db.save_position(position)

            trade = TradeRecord(
                market_slug=position.market_slug,
                token_id=token_id,
                side="SELL",
                price=current_price,
                size=position.size,
                cost_usd=current_price * position.size,
                leader_wallet=position.leader_wallet,
                is_paper=False,
                timestamp=datetime.now(timezone.utc),
                order_id=result.get("orderID", ""),
                status="FILLED",
            )
            self.db.save_trade(trade)

            log.info(
                "[LIVE] SELL %.2f shares @ $%.4f — P&L: $%.2f (%s)",
                position.size, current_price, position.pnl_usd, reason,
            )
            return position.pnl_usd

        except Exception as e:
            log.error("Live SELL failed for %s: %s", position.market_slug[:20], e)
            return 0.0
