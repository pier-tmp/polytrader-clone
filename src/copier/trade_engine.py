"""
Trade Engine — Dispatcher that routes signals to Paper or Live engine.
This is the main entry point for the copier module.
"""
import logging

from src import config
from src.models import TradeSignal, Position
from src.api.clob_client import ClobClient
from src.db.storage import Storage
from src.guards.chain import GuardChain
from src.copier.paper_engine import PaperEngine
from src.copier.live_engine import LiveEngine

log = logging.getLogger(__name__)


class TradeEngine:
    """
    Orchestrates the copy-trading flow:
    1. Receives a TradeSignal from the monitor
    2. Runs it through the guard chain
    3. Dispatches to Paper or Live engine
    4. Returns the resulting Position (or None if blocked)
    """

    def __init__(
        self,
        clob: ClobClient,
        storage: Storage,
        guard_chain: GuardChain,
        data_client=None,
    ):
        self.clob = clob
        self.db = storage
        self.guards = guard_chain
        self.is_paper = config.TRADING_MODE == "paper"

        if self.is_paper:
            self.engine = PaperEngine(clob, storage, data_client=data_client)
            log.info("Trade engine initialized in PAPER mode (bankroll: $%.0f)", config.PAPER_BANKROLL)
        else:
            self.engine = LiveEngine(clob, storage)
            log.info("Trade engine initialized in LIVE mode (bankroll: $%.0f)", config.LIVE_BANKROLL)

    def process_signal(self, signal: TradeSignal) -> Position | None:
        """
        Main entry point — called by the trade monitor for every new signal.
        """
        log.info(
            "Processing signal: %s %s on '%s' (leader: %s)",
            signal.side,
            f"${signal.size_usd:.0f}" if signal.size_usd else "",
            signal.market.question[:50],
            signal.leader.name or signal.leader.wallet[:10],
        )

        # Run guard chain
        passed, reason, metadata = self.guards.evaluate(signal)

        if not passed:
            log.info("✗ Signal blocked by guard: %s", reason)
            # Record blocked trade for analytics
            from src.models import TradeRecord
            blocked = TradeRecord(
                market_slug=signal.market.slug,
                token_id=signal.token_id,
                side=signal.side,
                price=signal.price,
                size=0,
                cost_usd=0,
                leader_wallet=signal.leader.wallet,
                is_paper=self.is_paper,
                timestamp=signal.timestamp,
                status="BLOCKED",
                guard_blocked=reason,
            )
            self.db.save_trade(blocked)
            return None

        # Execute trade
        if signal.side == "BUY":
            return self.engine.execute_buy(signal, metadata)
        elif signal.side == "SELL":
            return self._handle_sell(signal, metadata)

        return None

    def _handle_sell(self, signal: TradeSignal, metadata: dict) -> Position | None:
        """
        Handle leader SELL signal — find our matching position and close it.
        """
        open_positions = self.db.get_open_positions(is_paper=self.is_paper)
        matching = [
            p for p in open_positions
            if p.leader_wallet == signal.leader.wallet
            and p.token_id == signal.token_id
        ]

        if not matching:
            log.debug("No matching position for leader sell on %s", signal.market.slug[:20])
            return None

        for pos in matching:
            pnl = self.engine.execute_sell(pos, reason="leader_exit")
            log.info("Closed position on leader exit — P&L: $%.2f", pnl)

        return matching[0] if matching else None

    @property
    def bankroll(self) -> float:
        return self.engine.bankroll
