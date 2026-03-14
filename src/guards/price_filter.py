"""
Price Filter — Blocks trades outside an optimal price range.
Low-price trades (<0.5¢) are noise; high-price trades (>40¢) have little upside.
"""
import logging

from src import config
from src.models import TradeSignal

log = logging.getLogger(__name__)


def check_price_filter(signal: TradeSignal) -> str:
    """
    Validate entry price is within the configured range.
    Returns empty string if OK, reason string if blocked.
    """
    price = signal.price
    if price < config.MIN_AVG_PRICE:
        return f"price_too_cheap ({price:.4f} < {config.MIN_AVG_PRICE})"
    if price > config.MAX_AVG_PRICE:
        return f"price_too_expensive ({price:.4f} > {config.MAX_AVG_PRICE})"
    return ""
