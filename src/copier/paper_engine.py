"""
Paper Engine — Simulates trade execution using real orderbook prices.
No real money is spent. All trades are recorded as paper trades.
"""
import logging
from datetime import datetime, timezone

from src import config
from src.models import TradeSignal, Position, TradeRecord
from src.api.clob_client import ClobClient
from src.db.storage import Storage

log = logging.getLogger(__name__)


class PaperEngine:
    """
    Simulates order execution by reading real prices from the CLOB
    and recording virtual trades in the database.
    """

    def __init__(self, clob: ClobClient, storage: Storage, data_client=None):
        self.clob = clob
        self.db = storage
        self.data = data_client
        self._bankroll = config.PAPER_BANKROLL

    @property
    def bankroll(self) -> float:
        """Current bankroll = initial - cost of open positions + realized P&L."""
        open_pos = self.db.get_open_positions(is_paper=True)
        invested = sum(p.cost_usd for p in open_pos)
        summary = self.db.get_pnl_summary(is_paper=True)
        realized = summary.get("total_pnl", 0) or 0
        return self._bankroll - invested + realized

    def execute_buy(self, signal: TradeSignal, metadata: dict = None) -> Position | None:
        """
        Simulate a BUY order.
        1. Calculate position size (% of bankroll)
        2. Estimate fill price from real orderbook
        3. Record paper trade and open position
        """
        # Calculate size — proportional to whale's allocation if enabled
        available = self.bankroll
        trade_budget = self._calculate_bet_amount(signal, available)

        if trade_budget < 1.0:
            log.warning("Paper bankroll too low: $%.2f", available)
            return None

        token_id = signal.token_id or signal.market.token_id

        # Get estimated fill from real orderbook
        fill_price = self.clob.estimate_fill_price(token_id, "BUY", trade_budget)
        if fill_price <= 0:
            log.warning("Could not estimate fill price for %s", token_id[:12])
            return None

        shares = trade_budget / fill_price
        cost = trade_budget

        # Record trade
        trade = TradeRecord(
            market_slug=signal.market.slug,
            token_id=token_id,
            side="BUY",
            price=fill_price,
            size=shares,
            cost_usd=cost,
            leader_wallet=signal.leader.wallet,
            is_paper=True,
            timestamp=datetime.now(timezone.utc),
            status="FILLED",
        )
        self.db.save_trade(trade)

        # Open position
        position = Position(
            market_slug=signal.market.slug,
            token_id=token_id,
            side="BUY",
            entry_price=fill_price,
            size=shares,
            cost_usd=cost,
            current_price=fill_price,
            high_price=fill_price,
            leader_wallet=signal.leader.wallet,
            opened_at=datetime.now(timezone.utc),
            is_paper=True,
            status="OPEN",
        )
        self.db.save_position(position)

        log.info(
            "[PAPER] BUY %.2f shares @ $%.4f = $%.2f on %s (leader: %s)",
            shares, fill_price, cost,
            signal.market.slug[:30],
            signal.leader.name or signal.leader.wallet[:10],
        )
        return position

    def _calculate_bet_amount(self, signal: TradeSignal, available: float) -> float:
        """
        Calculate bet size. If whale sizing is enabled, replicate the whale's
        portfolio allocation percentage. Otherwise fall back to fixed %.
        """
        if config.WHALE_SIZING_ENABLED and self.data:
            try:
                portfolio = self.data.get_portfolio_value(signal.leader.wallet)
                whale_total = float(portfolio.get("value", portfolio.get("totalValue", 0)))
                if whale_total > 0:
                    whale_pct = signal.size_usd / whale_total
                    amount = available * whale_pct
                    max_cap = available * (config.WHALE_SIZING_MAX_PCT / 100.0)
                    amount = max(1.0, min(amount, max_cap))
                    log.debug(
                        "Whale sizing: whale %.1f%% of $%.0f → our $%.2f",
                        whale_pct * 100, whale_total, amount,
                    )
                    return amount
            except Exception as e:
                log.warning("Whale sizing failed, using fixed %%: %s", e)

        return available * (config.BET_SIZE_PERCENT / 100.0)

    def execute_sell(self, position: Position, reason: str = "leader_exit") -> float:
        """
        Simulate closing a position.
        Returns realized P&L.
        """
        token_id = position.token_id
        current_price = self.clob.get_price(token_id, "SELL")
        if current_price <= 0:
            current_price = self.clob.get_midpoint(token_id)

        position.update_pnl(current_price)
        position.closed_at = datetime.now(timezone.utc)
        position.close_reason = reason
        position.status = "CLOSED"
        self.db.save_position(position)

        # Record sell trade
        trade = TradeRecord(
            market_slug=position.market_slug,
            token_id=token_id,
            side="SELL",
            price=current_price,
            size=position.size,
            cost_usd=current_price * position.size,
            leader_wallet=position.leader_wallet,
            is_paper=True,
            timestamp=datetime.now(timezone.utc),
            status="FILLED",
        )
        self.db.save_trade(trade)

        log.info(
            "[PAPER] SELL %.2f shares @ $%.4f — P&L: $%.2f (%s) on %s",
            position.size, current_price, position.pnl_usd,
            reason, position.market_slug[:30],
        )
        return position.pnl_usd
