"""
Market Quality Filter — Blocks low-quality markets.
Checks liquidity, spread, and price bounds.
"""
import logging

from src import config
from src.models import TradeSignal
from src.api.clob_client import ClobClient

log = logging.getLogger(__name__)


def check_market_quality(signal: TradeSignal, clob: ClobClient) -> str:
    """
    Validate market quality. Returns empty string if OK,
    or the reason string if blocked.
    """
    # 1. Minimum liquidity
    if config.LIQUIDITY_GUARD and signal.market.liquidity < config.MIN_MARKET_LIQUIDITY:
        return f"low_liquidity ({signal.market.liquidity:.0f} < {config.MIN_MARKET_LIQUIDITY})"

    # 2. Price bounds — avoid extreme odds
    if config.PRICE_BOUNDS_GUARD:
        price = signal.price
        if price < config.MIN_ODDS:
            return f"price_too_low ({price:.3f} < {config.MIN_ODDS})"
        if price > config.MAX_ODDS:
            return f"price_too_high ({price:.3f} > {config.MAX_ODDS})"

    # 3. Spread check — wide spread = bad fill
    token_id = signal.token_id or signal.market.token_id
    if config.SPREAD_GUARD and token_id:
        try:
            spread_data = clob.get_spread(token_id)
            bid = float(spread_data.get("bid", 0))
            ask = float(spread_data.get("ask", 0))
            if bid > 0 and ask > 0:
                spread_pct = ((ask - bid) / ask) * 100
                if spread_pct > config.MAX_SPREAD_PERCENT:
                    return f"wide_spread ({spread_pct:.1f}% > {config.MAX_SPREAD_PERCENT}%)"
        except Exception as e:
            log.warning("Spread check failed for %s: %s", token_id[:12], e)

    # 4. Book depth — ensure enough liquidity to fill our order
    if config.BOOK_DEPTH_GUARD and token_id:
        try:
            depth = clob.get_book_depth(token_id, signal.side)
            if depth < signal.size_usd * 2:
                return f"thin_book (depth ${depth:.0f} vs trade ${signal.size_usd:.0f})"
        except Exception:
            pass

    return ""  # All checks passed
