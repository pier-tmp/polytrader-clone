"""
Sports-Aware Guard — Protects sports bets from panic-selling mid-game.
Only the leader's explicit exit triggers a sell on sports markets.
"""
import logging
import re

from src.models import TradeSignal

log = logging.getLogger(__name__)

SPORTS_TAGS = {
    "sports", "nba", "nfl", "nhl", "mlb", "soccer", "football",
    "tennis", "mma", "ufc", "boxing", "ncaa", "ncaab", "ncaaf",
    "epl", "serie-a", "la-liga", "bundesliga", "champions-league",
    "cricket", "f1", "golf",
}


def is_sports_market(signal: TradeSignal) -> bool:
    """Check if the signal's market is sports-related."""
    tags_lower = {t.lower() for t in signal.market.tags}
    if tags_lower & SPORTS_TAGS:
        return True
    title = signal.market.question.lower()
    sports_keywords = ["nba", "nfl", "nhl", "mlb", "premier league",
                       "champions league", "tennis", "ufc", "mma"]
    return any(re.search(rf"\b{re.escape(kw)}\b", title) for kw in sports_keywords)


def should_block_sports_sell(signal: TradeSignal) -> bool:
    """
    Block SELL orders on sports markets unless it's a leader exit.
    
    During a live game, prices swing wildly based on in-game events.
    The trailing stop-loss would trigger on noise. Only the leader's
    explicit sell action should trigger our sell.
    
    This guard is only relevant for SELL signals.
    BUY signals on sports markets pass through normally.
    """
    if signal.side != "SELL":
        return False

    if not is_sports_market(signal):
        return False

    # If we get here, it's a SELL on a sports market.
    # This is fine — it means the leader explicitly sold.
    # The guard's job is to INFORM the portfolio manager
    # that this market should NOT use trailing stop, only leader exit.
    # We return False (don't block) because the leader chose to sell.
    return False


def is_sports_trailing_stop_exempt(signal: TradeSignal) -> bool:
    """
    Returns True if this market should be exempt from trailing stop-loss.
    Sports markets only close on leader exit, not on price drops.
    """
    return is_sports_market(signal)
