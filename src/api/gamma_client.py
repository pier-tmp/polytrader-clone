"""
Gamma API Client — Market discovery and metadata.
Public API, no authentication required.
Base URL: https://gamma-api.polymarket.com
"""
import logging
from typing import Optional
import requests

from src import config

log = logging.getLogger(__name__)


class GammaClient:
    """Wrapper for the Polymarket Gamma API (market metadata)."""

    def __init__(self, base_url: str = None):
        self.base = base_url or config.GAMMA_API
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _get(self, path: str, params: dict = None) -> dict | list:
        url = f"{self.base}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            log.error("Gamma API error %s: %s", path, e)
            return []

    # ── Markets ───────────────────────────────────────────

    def get_markets(
        self,
        closed: bool = False,
        limit: int = 100,
        offset: int = 0,
        tag_slug: str = None,
        order: str = "volume24hr",
        ascending: bool = False,
    ) -> list[dict]:
        """Fetch list of markets with optional filters."""
        params = {
            "closed": str(closed).lower(),
            "limit": limit,
            "offset": offset,
            "order": order,
            "ascending": str(ascending).lower(),
        }
        if tag_slug:
            params["tag_slug"] = tag_slug
        return self._get("/markets", params)

    def get_market(self, condition_id: str) -> dict:
        """Fetch single market by condition ID."""
        result = self._get("/markets", {"condition_id": condition_id})
        if isinstance(result, list) and result:
            return result[0]
        return result if isinstance(result, dict) else {}

    def get_market_by_slug(self, slug: str) -> dict:
        """Fetch single market by slug."""
        result = self._get("/markets", {"slug": slug})
        if isinstance(result, list) and result:
            return result[0]
        return {}

    # ── Events ────────────────────────────────────────────

    def get_events(self, limit: int = 50, closed: bool = False) -> list[dict]:
        """Fetch events (groups of related markets)."""
        return self._get("/events", {"limit": limit, "closed": str(closed).lower()})

    def get_event(self, event_id: str) -> dict:
        """Fetch single event by ID."""
        result = self._get(f"/events/{event_id}")
        return result if isinstance(result, dict) else {}

    # ── Tags ──────────────────────────────────────────────

    def get_tags(self) -> list[dict]:
        """Fetch all available tags."""
        return self._get("/tags")

    # ── Helpers ───────────────────────────────────────────

    def get_market_tags(self, condition_id: str) -> list[str]:
        """Return tag slugs for a market."""
        market = self.get_market(condition_id)
        if not market:
            return []
        tags = market.get("tags", [])
        if isinstance(tags, list):
            return [t.get("slug", "") if isinstance(t, dict) else str(t) for t in tags]
        return []

    def is_crypto_market(self, market: dict) -> bool:
        """Check if a market is in the crypto category."""
        tags = market.get("tags", [])
        crypto_slugs = {"crypto", "crypto-prices", "btc", "eth", "sol", "bitcoin", "ethereum"}
        for tag in tags:
            slug = tag.get("slug", "") if isinstance(tag, dict) else str(tag)
            if slug.lower() in crypto_slugs:
                return True
        title = market.get("question", "").lower()
        return any(kw in title for kw in ["bitcoin", "btc", "ethereum", "eth ", "solana", "sol "])

    def is_sports_market(self, market: dict) -> bool:
        """Check if a market is sports-related."""
        sports_slugs = {
            "sports", "nba", "nfl", "nhl", "mlb", "soccer", "football",
            "tennis", "mma", "ufc", "boxing", "ncaa", "epl", "serie-a",
            "champions-league", "cricket",
        }
        tags = market.get("tags", [])
        for tag in tags:
            slug = tag.get("slug", "") if isinstance(tag, dict) else str(tag)
            if slug.lower() in sports_slugs:
                return True
        return False
