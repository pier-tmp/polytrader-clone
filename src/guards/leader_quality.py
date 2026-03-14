"""
Leader Quality Filter — Validates that the leader is still performing.
Re-checks KPIs before copying each trade.
"""
import logging
from datetime import datetime, timedelta, timezone

from src import config
from src.models import TradeSignal, Leader
from src.db.storage import Storage

log = logging.getLogger(__name__)


def check_leader_quality(signal: TradeSignal, storage: Storage) -> str:
    """
    Quick re-validation of the leader before copying.
    Returns empty string if OK, reason string if blocked.
    
    This is a lightweight check (no API calls) using cached data.
    The full evaluation happens during the 24h scan.
    """
    leader = signal.leader

    # 1. Still active in our database?
    if not leader.active:
        return "leader_inactive"

    # 2. Win rate still above threshold
    if leader.win_rate < config.MIN_WIN_RATE:
        return f"leader_low_wr ({leader.win_rate:.1f}% < {config.MIN_WIN_RATE}%)"

    # 2b. Leader must have appeared in enough consecutive scans
    if leader.scan_count < config.MIN_SCAN_COUNT:
        return f"leader_new ({leader.scan_count} scans < {config.MIN_SCAN_COUNT} required)"

    # 3. Scan not too stale (allow 2x scan interval before warning)
    max_age = timedelta(hours=config.SCAN_INTERVAL_HOURS * 2)
    if datetime.now(timezone.utc) - leader.last_scanned > max_age:
        log.warning(
            "Leader %s scan data is stale (%s)",
            leader.wallet[:10],
            leader.last_scanned.isoformat(),
        )
        # Don't block, just warn — the scan will update on next cycle

    # 4. Don't copy the same market we already have a position in
    open_positions = storage.get_open_positions(
        is_paper=(config.TRADING_MODE == "paper")
    )
    for pos in open_positions:
        if (pos.token_id == signal.token_id and
                pos.leader_wallet == leader.wallet):
            return "already_in_position"

    return ""  # All checks passed
