"""
Price Filter — Blocks trades with prices too low to be meaningful.
Low-price trades (<0.5¢) are noise.
"""
import logging

from src import config
from src.models import TradeSignal

log = logging.getLogger(__name__)


def check_price_filter(signal: TradeSignal) -> str:
    """
    Validate entry price is not too cheap.
    Returns empty string if OK, reason string if blocked.
    """
    price = signal.price
    if price < config.MIN_AVG_PRICE:
        return f"price_too_cheap ({price:.4f} < {config.MIN_AVG_PRICE})"
    return ""
