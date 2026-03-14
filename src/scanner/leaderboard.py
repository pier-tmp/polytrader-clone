"""
Leaderboard Scanner — Discovers top-performing wallets and filters by KPIs.
Runs every 24h, updates the active leaders list.
"""
import logging
from datetime import datetime, timezone

from src import config
from src.models import Leader
from src.api.gamma_client import GammaClient
from src.api.data_client import DataClient
from src.db.storage import Storage

log = logging.getLogger(__name__)


class LeaderboardScanner:
    """
    Scans the Polymarket leaderboard and selects leaders
    that pass quality filters.
    
    Filters:
    - Win rate >= MIN_WIN_RATE (default 55%)
    - Volume >= MIN_VOLUME_USD (default $5K)
    - Crypto ratio <= MAX_CRYPTO_RATIO (default 40%)
    - Preferred category ratio >= MIN_PREFERRED_RATIO (if PREFERRED_CATEGORIES set)
    - Max MAX_LEADERS selected (default 10)
    """

    def __init__(
        self,
        data_client: DataClient,
        gamma_client: GammaClient,
        storage: Storage,
    ):
        self.data = data_client
        self.gamma = gamma_client
        self.db = storage

    def scan(self) -> list[Leader]:
        """
        Full scan cycle:
        1. Fetch leaderboard from Data API
        2. For each candidate, compute detailed stats
        3. Filter by quality criteria
        4. Save to database, deactivate old leaders
        """
        log.info("Starting leaderboard scan...")

        # Fetch raw leaderboard (top by monthly P&L)
        raw = self.data.get_leaderboard(
            period="MONTH",
            sort_by="PNL",
            limit=50,
        )
        log.info("Fetched %d leaderboard entries", len(raw))

        candidates = []
        for entry in raw:
            wallet = entry.get("userAddress", entry.get("proxyWallet", ""))
            if not wallet:
                continue

            leader = self._evaluate_candidate(wallet, entry)
            if not leader:
                continue
            label = leader.name or leader.wallet[:10]
            pref_str = f", Pref: {leader.preferred_ratio*100:.0f}%" if config.PREFERRED_CATEGORIES else ""
            stats = (
                "WR: %.1f%%, Vol: $%.0f, PnL: $%.0f, Crypto: %.0f%%%s"
                % (leader.win_rate, leader.volume_usd, leader.pnl_usd,
                   leader.crypto_ratio * 100, pref_str)
            )
            if self._passes_filters(leader):
                candidates.append(leader)
                log.info("  ✓ %s — %s", label, stats)
            else:
                log.info("  ✗ %s — %s", label, stats)

            if len(candidates) >= config.MAX_LEADERS:
                break

        # Sort by P&L descending, take top N
        candidates.sort(key=lambda l: l.pnl_usd, reverse=True)
        selected = candidates[: config.MAX_LEADERS]

        # Update database — increment scan_count for returning leaders, reset for new
        self.db.deactivate_all_leaders()
        for leader in selected:
            prev_count = self.db.get_leader_scan_count(leader.wallet)
            leader.scan_count = prev_count + 1
            leader.active = True
            self.db.save_leader(leader)

        log.info("Scan complete: %d leaders selected", len(selected))
        return selected

    def _evaluate_candidate(self, wallet: str, entry: dict) -> Leader | None:
        """Build a Leader object with computed stats."""
        try:
            # Use name from leaderboard entry first, fall back to profile lookup
            name = entry.get("userName", entry.get("pseudonym", ""))
            if not name:
                profile = self.data.get_profile(wallet)
                name = profile.get("name", profile.get("pseudonym", ""))

            # Win rate from closed positions
            win_rate = self.data.compute_win_rate(wallet)

            # Volume and PnL from leaderboard entry
            volume = float(entry.get("vol", entry.get("volume", 0)))
            pnl = float(entry.get("pnl", entry.get("profit", 0)))
            total_trades = int(entry.get("numTrades", entry.get("markets_traded", 0)))

            # Category ratios (expensive — calls Gamma per trade, cached per cid)
            # Only compute for candidates that pass basic filters first
            crypto_ratio = 0.0
            preferred_ratio = 0.0
            if win_rate >= config.MIN_WIN_RATE and volume >= config.MIN_VOLUME_USD:
                ratios = self.data.compute_category_ratios(wallet, self.gamma)
                crypto_ratio = ratios["crypto_ratio"]
                # Compute preferred category ratio if configured
                if config.PREFERRED_CATEGORIES:
                    cat_counts = ratios["category_counts"]
                    total_cat = sum(cat_counts.values()) or 1
                    preferred_count = sum(
                        v for k, v in cat_counts.items()
                        if k in config.PREFERRED_CATEGORIES
                    )
                    preferred_ratio = preferred_count / total_cat

            return Leader(
                wallet=wallet,
                name=name,
                win_rate=win_rate,
                volume_usd=volume,
                pnl_usd=pnl,
                total_trades=total_trades,
                crypto_ratio=crypto_ratio,
                preferred_ratio=preferred_ratio,
                last_scanned=datetime.now(timezone.utc),
            )
        except Exception as e:
            log.warning("Failed to evaluate %s: %s", wallet[:10], e)
            return None

    def _passes_filters(self, leader: Leader) -> bool:
        """Apply quality filters."""
        if leader.win_rate < config.MIN_WIN_RATE:
            log.info("    filter: low win rate: %.1f%% (min %d%%)", leader.win_rate, config.MIN_WIN_RATE)
            return False
        if leader.volume_usd < config.MIN_VOLUME_USD:
            log.info("    filter: low volume: $%.0f (min $%d)", leader.volume_usd, config.MIN_VOLUME_USD)
            return False
        if leader.crypto_ratio > config.MAX_CRYPTO_RATIO:
            log.info("    filter: high crypto ratio: %.0f%% (max %.0f%%)", leader.crypto_ratio * 100, config.MAX_CRYPTO_RATIO * 100)
            return False
        if config.PREFERRED_CATEGORIES and leader.preferred_ratio < config.MIN_PREFERRED_RATIO:
            log.info(
                "    filter: low preferred ratio: %.0f%% (min %.0f%%, want: %s)",
                leader.preferred_ratio * 100, config.MIN_PREFERRED_RATIO * 100,
                ",".join(config.PREFERRED_CATEGORIES),
            )
            return False
        return True
