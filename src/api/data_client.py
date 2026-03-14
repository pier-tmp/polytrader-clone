"""
Data API Client — Leaderboard, user activity, positions, trades.
Public API, no authentication required.
Base URL: https://data-api.polymarket.com
"""
import logging
from typing import Optional
import requests

from src import config

log = logging.getLogger(__name__)


class DataClient:
    """Wrapper for the Polymarket Data API (user data & leaderboard)."""

    def __init__(self, base_url: str = None):
        self.base = base_url or config.DATA_API
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _get(self, path: str, params: dict = None) -> dict | list:
        url = f"{self.base}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            log.error("Data API error %s: %s", path, e)
            return []

    # ── Leaderboard ───────────────────────────────────────

    def get_leaderboard(
        self,
        period: str = "MONTH",     # "DAY", "WEEK", "MONTH", "ALL"
        sort_by: str = "PNL",      # "PNL", "VOL"
        limit: int = 50,
        offset: int = 0,
        category: str = "OVERALL", # "OVERALL", "POLITICS", "SPORTS", "CRYPTO", etc.
    ) -> list[dict]:
        """Fetch trader leaderboard rankings."""
        return self._get("/v1/leaderboard", {
            "timePeriod": period,
            "orderBy": sort_by,
            "category": category,
            "limit": min(limit, 50),
            "offset": offset,
        })

    # ── Profile ───────────────────────────────────────────

    def get_profile(self, wallet: str) -> dict:
        """Fetch public profile by wallet address (via Gamma API)."""
        url = f"{config.GAMMA_API}/public-profile"
        try:
            resp = self.session.get(url, params={"address": wallet.lower()}, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            log.error("Profile API error for %s: %s", wallet[:12], e)
            return {}

    # ── Activity ──────────────────────────────────────────

    def get_activity(
        self,
        wallet: str,
        trade_type: str = "TRADE",
        limit: int = 100,
        offset: int = 0,
        start: Optional[int] = None,
        end: Optional[int] = None,
        market: Optional[str] = None,
        side: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch on-chain activity for a wallet.
        Returns trades, splits, merges, redemptions.
        """
        params = {
            "user": wallet.lower(),
            "type": trade_type,
            "limit": limit,
            "offset": offset,
            "sortBy": "TIMESTAMP",
            "sortDirection": "DESC",
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if market:
            params["market"] = market
        if side:
            params["side"] = side
        return self._get("/activity", params)

    def get_recent_trades(
        self,
        wallet: str,
        since_timestamp: int = 0,
        limit: int = 50,
    ) -> list[dict]:
        """Fetch trades for a wallet since a given timestamp."""
        return self.get_activity(
            wallet=wallet,
            trade_type="TRADE",
            limit=limit,
            start=since_timestamp if since_timestamp else None,
        )

    # ── Positions ─────────────────────────────────────────

    def get_positions(self, wallet: str, limit: int = 100) -> list[dict]:
        """Fetch current open positions for a wallet."""
        return self._get("/positions", {
            "user": wallet.lower(),
            "limit": limit,
            "sizeThreshold": 0,
        })

    def get_closed_positions(self, wallet: str, limit: int = 50) -> list[dict]:
        """Fetch closed/resolved positions for a wallet."""
        return self._get("/closed-positions", {
            "user": wallet.lower(),
            "limit": min(limit, 50),
            "sortBy": "REALIZEDPNL",
            "sortDirection": "DESC",
        })

    # ── Trades by market ──────────────────────────────────

    def get_market_trades(
        self,
        condition_id: str,
        limit: int = 100,
    ) -> list[dict]:
        """Fetch recent trades for a specific market."""
        return self._get("/trades", {
            "market": condition_id,
            "limit": limit,
        })

    # ── Portfolio value ───────────────────────────────────

    def get_portfolio_value(self, wallet: str) -> dict:
        """Fetch total value of a user's positions."""
        result = self._get("/value", {"user": wallet.lower()})
        return result if isinstance(result, dict) else {}

    # ── Market holders ────────────────────────────────────

    def get_holders(self, condition_id: str, limit: int = 50) -> list[dict]:
        """Fetch top holders for a market."""
        return self._get("/holders", {
            "market": condition_id,
            "limit": limit,
        })

    # ── Helpers ───────────────────────────────────────────

    def compute_win_rate(self, wallet: str) -> float:
        """
        Calculate win rate from closed positions.
        Returns percentage (0-100).
        """
        closed = self.get_closed_positions(wallet, limit=50)
        if not closed:
            return 0.0
        wins = sum(1 for p in closed if float(p.get("realizedPnl", p.get("cashPnl", p.get("pnl", 0)))) > 0)
        return (wins / len(closed)) * 100.0

    def compute_crypto_ratio(self, wallet: str, gamma_client=None) -> float:
        """
        Ratio of crypto-tagged trades to total trades.
        Requires a GammaClient to check market tags.
        """
        if not gamma_client:
            return 0.0
        trades = self.get_activity(wallet, limit=200)
        if not trades:
            return 0.0
        crypto_count = 0
        for trade in trades:
            cid = trade.get("conditionId", "")
            if cid:
                market = gamma_client.get_market(cid)
                if market and gamma_client.is_crypto_market(market):
                    crypto_count += 1
        return crypto_count / len(trades)
