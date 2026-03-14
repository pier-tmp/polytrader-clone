"""
Trade Monitor — Watches active leaders for new trades.
Polls the Data API every POLL_INTERVAL_SECONDS and emits TradeSignals.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Callable

from src import config
from src.models import TradeSignal, Leader, Market
from src.api.data_client import DataClient
from src.api.gamma_client import GammaClient
from src.db.storage import Storage

log = logging.getLogger(__name__)


class TradeMonitor:
    """
    Monitors active leaders for new trades via polling.
    When a new trade is detected, builds a TradeSignal
    and passes it to the callback for processing.
    """

    def __init__(
        self,
        data_client: DataClient,
        gamma_client: GammaClient,
        storage: Storage,
        on_signal: Callable[[TradeSignal], None] = None,
    ):
        self.data = data_client
        self.gamma = gamma_client
        self.db = storage
        self.on_signal = on_signal
        self._running = False

    def start(self):
        """Start the polling loop. Blocks the current thread."""
        self._running = True
        log.info(
            "Trade monitor started — polling every %ds",
            config.POLL_INTERVAL_SECONDS,
        )

        while self._running:
            try:
                self._poll_cycle()
            except Exception as e:
                log.error("Poll cycle error: %s", e)
            time.sleep(config.POLL_INTERVAL_SECONDS)

    def stop(self):
        """Stop the polling loop."""
        self._running = False
        log.info("Trade monitor stopped")

    def _poll_cycle(self):
        """One poll cycle: check all active leaders for new trades."""
        leaders = self.db.get_active_leaders()
        if not leaders:
            log.debug("No active leaders to monitor")
            return

        for leader in leaders:
            self._check_leader(leader)

    def _check_leader(self, leader: Leader):
        """Check a single leader for new trades since last seen."""
        last_ts = self.db.get_last_seen_ts(leader.wallet)
        now_ts = int(datetime.now(timezone.utc).timestamp())

        trades = self.data.get_recent_trades(
            wallet=leader.wallet,
            since_timestamp=last_ts + 1 if last_ts else now_ts - config.POLL_INTERVAL_SECONDS,
            limit=20,
        )

        if not trades:
            return

        new_count = 0
        max_ts = last_ts

        for trade in trades:
            ts = int(trade.get("timestamp", 0))
            if ts <= last_ts:
                continue

            signal = self._build_signal(leader, trade)
            if signal and self.on_signal:
                self.on_signal(signal)
                new_count += 1

            if ts > max_ts:
                max_ts = ts

        if max_ts > last_ts:
            self.db.set_last_seen_ts(leader.wallet, max_ts)

        if new_count:
            log.info(
                "Leader %s: %d new trade(s) detected",
                leader.name or leader.wallet[:10],
                new_count,
            )

    def _build_signal(self, leader: Leader, trade: dict) -> TradeSignal | None:
        """Convert a raw trade dict into a TradeSignal."""
        try:
            condition_id = trade.get("conditionId", "")
            side = trade.get("side", "BUY").upper()
            size_usd = float(trade.get("usdcSize", trade.get("size", 0)))
            price = float(trade.get("price", 0))
            token_id = trade.get("asset", "")
            slug = trade.get("slug", "")
            title = trade.get("title", "")
            timestamp_raw = trade.get("timestamp", 0)

            # Get market metadata from Gamma
            market_data = self.gamma.get_market(condition_id) if condition_id else {}
            tags = market_data.get("tags", [])
            end_date_str = market_data.get("endDate") or market_data.get("end_date_iso")
            end_date = None
            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            # Fallback chain for liquidity — Gamma API may use different field names
            raw_liq = (
                market_data.get("liquidity")
                or market_data.get("liquidityNum")
                or market_data.get("liquidityClob")
                or 0
            )
            raw_vol = (
                market_data.get("volume24hr")
                or market_data.get("volume24hrClob")
                or 0
            )

            try:
                liquidity_val = float(raw_liq)
            except (ValueError, TypeError):
                liquidity_val = 0.0

            try:
                volume_val = float(raw_vol)
            except (ValueError, TypeError):
                volume_val = 0.0

            market = Market(
                condition_id=condition_id,
                token_id=token_id,
                question=title or market_data.get("question", ""),
                slug=slug or market_data.get("slug", ""),
                tags=[
                    t.get("slug", "") if isinstance(t, dict) else str(t)
                    for t in tags
                ],
                end_date=end_date,
                volume_24h=volume_val,
                liquidity=liquidity_val,
                outcome=trade.get("outcome", ""),
            )

            return TradeSignal(
                leader=leader,
                market=market,
                side=side,
                token_id=token_id,
                size_usd=size_usd,
                price=price,
                timestamp=datetime.fromtimestamp(timestamp_raw, tz=timezone.utc)
                if isinstance(timestamp_raw, (int, float)) and timestamp_raw > 0
                else datetime.now(timezone.utc),
            )

        except Exception as e:
            log.warning("Failed to build signal: %s", e)
            return None
