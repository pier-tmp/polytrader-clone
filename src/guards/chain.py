"""
Guard Chain — Orchestrates all trade protections.
Each signal must pass ALL guards before being copied.
"""
import logging

from src import config
from src.models import TradeSignal
from src.api.clob_client import ClobClient
from src.db.storage import Storage
from src.guards.coinflip_filter import is_coinflip
from src.guards.sports_aware import should_block_sports_sell, is_sports_trailing_stop_exempt
from src.guards.market_quality import check_market_quality

log = logging.getLogger(__name__)


class GuardChain:
    """
    Runs all guards sequentially on a TradeSignal.
    Returns (passed: bool, reason: str, metadata: dict).
    """

    def __init__(self, clob: ClobClient, storage: Storage):
        self.clob = clob
        self.storage = storage

    def evaluate(self, signal: TradeSignal) -> tuple[bool, str, dict]:
        """
        Run all guards on a signal.
        Returns:
            (True, "", metadata)  — all guards passed
            (False, reason, {})   — blocked by a guard
        """
        metadata = {}

        # 1. Coinflip protection
        if config.COINFLIP_BLOCK and is_coinflip(signal):
            return False, "coinflip_blocked", {}

        # 2. Sports-aware logic
        if config.SPORTS_AWARE:
            if should_block_sports_sell(signal):
                return False, "sports_sell_blocked", {}
            metadata["sports_exempt_trailing_stop"] = is_sports_trailing_stop_exempt(signal)

        # 3. Market quality
        market_reason = check_market_quality(signal, self.clob)
        if market_reason:
            return False, market_reason, {}

        # 4. Duplicate / overlap checks
        if config.OVERLAP_GUARD:
            open_positions = self.storage.get_open_positions(
                is_paper=(config.TRADING_MODE == "paper")
            )
            for pos in open_positions:
                if (pos.token_id == signal.token_id and
                        pos.leader_wallet == signal.leader.wallet):
                    return False, "already_in_position", {}
                if pos.market_slug == signal.market.slug and pos.side != signal.side:
                    return False, "event_overlap (opposite side open)", {}

        log.info(
            "✓ All guards passed: %s %s on %s",
            signal.side,
            signal.market.question[:40],
            signal.leader.name or signal.leader.wallet[:10],
        )
        return True, "", metadata
