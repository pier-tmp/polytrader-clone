"""
Guard Chain — Orchestrates trade protections.
Each signal must pass ALL guards before being copied.

Note: category-level filtering (sports, crypto, coinflip) is handled
upstream in the leaderboard scanner via PREFERRED_CATEGORIES.
Guards here focus on per-trade quality checks.
"""
import logging

from src import config
from src.models import TradeSignal
from src.api.clob_client import ClobClient
from src.db.storage import Storage
from src.guards.market_quality import check_market_quality
from src.guards.price_filter import check_price_filter

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

        # 1. Price filter (optional)
        if config.PRICE_FILTER_ENABLED and signal.side == "BUY":
            price_reason = check_price_filter(signal)
            if price_reason:
                return False, price_reason, {}

        # 2. Market quality
        market_reason = check_market_quality(signal, self.clob)
        if market_reason:
            return False, market_reason, {}

        # 3. Duplicate / overlap checks
        open_positions = self.storage.get_open_positions(
            is_paper=(config.TRADING_MODE == "paper")
        )
        for pos in open_positions:
            # Already in this exact position from same leader
            if (pos.token_id == signal.token_id and
                    pos.leader_wallet == signal.leader.wallet):
                return False, "already_in_position", {}
            # Opposite side on same market
            if pos.market_slug == signal.market.slug and pos.side != signal.side:
                return False, "event_overlap (opposite side open)", {}

        log.info(
            "✓ All guards passed: %s %s on %s",
            signal.side,
            signal.market.question[:40],
            signal.leader.name or signal.leader.wallet[:10],
        )
        return True, "", metadata
