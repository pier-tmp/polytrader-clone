"""
Coinflip Filter — Blocks crypto speed markets (5min/15min BTC up/down).
"""
import logging
from datetime import datetime, timezone

from src.models import TradeSignal

log = logging.getLogger(__name__)

COINFLIP_PATTERNS = [
    "5-minute", "5 minute", "15-minute", "15 minute",
    "speed market", "up or down", "up/down",
    "will bitcoin go up", "will btc be above", "will btc be below",
    "will eth go up", "will eth be above", "will sol go up",
    "next 5 min", "next 15 min", "next 30 min",
]

CRYPTO_TAGS = {"crypto", "crypto-prices", "btc", "eth", "sol", "bitcoin", "ethereum"}


def is_coinflip(signal: TradeSignal) -> bool:
    """Returns True if the market is a coinflip that should be blocked."""
    title = signal.market.question.lower()

    # Pattern match on title
    if any(p in title for p in COINFLIP_PATTERNS):
        log.debug("Coinflip blocked (title): %s", title[:60])
        return True

    # Crypto + short expiry
    tags_lower = {t.lower() for t in signal.market.tags}
    is_crypto = bool(tags_lower & CRYPTO_TAGS)

    if is_crypto and signal.market.end_date:
        now = datetime.now(timezone.utc)
        end = signal.market.end_date
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        minutes_left = (end - now).total_seconds() / 60
        if minutes_left < 30:
            log.debug("Coinflip blocked (crypto + %d min left): %s", minutes_left, title[:60])
            return True

    return False
