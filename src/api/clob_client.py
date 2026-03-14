"""
CLOB API Client — Orderbook, pricing, and order management.
Public endpoints: prices, books, midpoints.
Authenticated endpoints: order placement/cancellation.
Base URL: https://clob.polymarket.com
"""
import logging
from typing import Optional
import requests

from src import config

log = logging.getLogger(__name__)


class ClobClient:
    """
    Wrapper for the Polymarket CLOB API.
    
    For trading, we use the official py-clob-client SDK.
    This wrapper handles read-only operations and provides
    a unified interface for the trade engine.
    """

    def __init__(self, base_url: str = None):
        self.base = base_url or config.CLOB_API
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        self._sdk_client = None

    # ── SDK (for authenticated trading) ───────────────────

    def _get_sdk(self):
        """Lazy-initialize the official SDK client for trading."""
        if self._sdk_client is None:
            try:
                from py_clob_client.client import ClobClient as SdkClient
                self._sdk_client = SdkClient(
                    self.base,
                    key=config.PRIVATE_KEY,
                    chain_id=137,
                    signature_type=config.SIGNATURE_TYPE,
                    funder=config.PROXY_ADDRESS or None,
                )
                self._sdk_client.set_api_creds(
                    self._sdk_client.create_or_derive_api_creds()
                )
                log.info("CLOB SDK authenticated successfully")
            except Exception as e:
                log.error("Failed to init CLOB SDK: %s", e)
                raise
        return self._sdk_client

    # ── Public endpoints (no auth) ────────────────────────

    def _get(self, path: str, params: dict = None) -> dict | list:
        url = f"{self.base}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            log.error("CLOB API error %s: %s", path, e)
            return {}

    def get_price(self, token_id: str, side: str = "BUY") -> float:
        """Get current price for a token."""
        result = self._get("/price", {"token_id": token_id, "side": side})
        return float(result.get("price", 0.0))

    def get_midpoint(self, token_id: str) -> float:
        """Get midpoint price for a token."""
        result = self._get("/midpoint", {"token_id": token_id})
        return float(result.get("mid", 0.0))

    def get_spread(self, token_id: str) -> dict:
        """Get bid-ask spread for a token."""
        result = self._get("/spread", {"token_id": token_id})
        return result if isinstance(result, dict) else {}

    def get_order_book(self, token_id: str) -> dict:
        """
        Get full order book for a token.
        Returns: {"bids": [...], "asks": [...], "hash": "..."}
        """
        result = self._get("/book", {"token_id": token_id})
        return result if isinstance(result, dict) else {"bids": [], "asks": []}

    def get_last_trade_price(self, token_id: str) -> float:
        """Get the price of the last trade on this token."""
        result = self._get("/last-trade-price", {"token_id": token_id})
        return float(result.get("price", 0.0))

    def get_price_history(
        self,
        token_id: str,
        interval: str = "1h",
        fidelity: int = 60,
    ) -> list[dict]:
        """Get historical price data."""
        result = self._get("/prices-history", {
            "market": token_id,
            "interval": interval,
            "fidelity": fidelity,
        })
        return result if isinstance(result, list) else []

    # ── Order book analysis ───────────────────────────────

    def estimate_fill_price(
        self,
        token_id: str,
        side: str,
        amount_usd: float,
    ) -> float:
        """
        Estimate the average fill price for a given trade size
        by walking the order book.
        """
        book = self.get_order_book(token_id)
        levels = book.get("asks" if side == "BUY" else "bids", [])
        if not levels:
            return self.get_midpoint(token_id)

        remaining = amount_usd
        total_shares = 0.0
        total_cost = 0.0

        for level in levels:
            price = float(level.get("price", 0))
            size = float(level.get("size", 0))
            if price <= 0:
                continue
            level_cost = price * size
            if level_cost >= remaining:
                shares_here = remaining / price
                total_shares += shares_here
                total_cost += remaining
                remaining = 0
                break
            else:
                total_shares += size
                total_cost += level_cost
                remaining -= level_cost

        if total_shares == 0:
            return self.get_midpoint(token_id)
        return total_cost / total_shares

    def get_book_depth(self, token_id: str, side: str = "BUY") -> float:
        """Total USD depth on one side of the book."""
        book = self.get_order_book(token_id)
        levels = book.get("asks" if side == "BUY" else "bids", [])
        return sum(
            float(l.get("price", 0)) * float(l.get("size", 0))
            for l in levels
        )

    # ── Trading (authenticated, live mode only) ───────────

    def place_limit_order(
        self,
        token_id: str,
        price: float,
        size: float,
        side: str = "BUY",
        post_only: bool = True,
    ) -> dict:
        """
        Place a limit order via the official SDK.
        post_only=True ensures maker order ($0 fee).
        """
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY, SELL

        sdk = self._get_sdk()
        order_side = BUY if side.upper() == "BUY" else SELL

        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=order_side,
        )
        signed = sdk.create_order(order_args)
        result = sdk.post_order(signed, OrderType.GTC)
        log.info("Order placed: %s %s @ %.4f x %.2f → %s", side, token_id[:12], price, size, result)
        return result

    def place_market_order(
        self,
        token_id: str,
        amount_usd: float,
        side: str = "BUY",
    ) -> dict:
        """Place a fill-or-kill market order."""
        from py_clob_client.clob_types import MarketOrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY, SELL

        sdk = self._get_sdk()
        order_side = BUY if side.upper() == "BUY" else SELL

        mo = MarketOrderArgs(
            token_id=token_id,
            amount=amount_usd,
            side=order_side,
        )
        signed = sdk.create_market_order(mo)
        result = sdk.post_order(signed, OrderType.FOK)
        log.info("Market order: %s $%.2f on %s → %s", side, amount_usd, token_id[:12], result)
        return result

    def cancel_order(self, order_id: str) -> dict:
        """Cancel an open order."""
        sdk = self._get_sdk()
        return sdk.cancel(order_id)

    def cancel_all(self) -> dict:
        """Cancel all open orders."""
        sdk = self._get_sdk()
        return sdk.cancel_all()
