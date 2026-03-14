"""
Polytrader Clone — Main Entry Point
Orchestrates: leaderboard scanner, trade monitor, portfolio manager, notifications.
"""
import logging
import sys
import time
import threading
import signal as sig
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config
from src.api.gamma_client import GammaClient
from src.api.data_client import DataClient
from src.api.clob_client import ClobClient
from src.db.storage import Storage
from src.scanner.leaderboard import LeaderboardScanner
from src.scanner.trade_monitor import TradeMonitor
from src.guards.chain import GuardChain
from src.copier.trade_engine import TradeEngine
from src.portfolio.manager import PortfolioManager
from src.notifications.telegram_bot import TelegramNotifier

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("polytrader")

# ── Globals ───────────────────────────────────────────────
_shutdown = threading.Event()


def main():
    mode = config.TRADING_MODE.upper()
    log.info("=" * 50)
    log.info("  POLYTRADER CLONE — %s MODE", mode)
    log.info("=" * 50)
    log.info("Bankroll: $%.0f", config.get_bankroll())
    log.info("Bet size: %.0f%% ($%.0f per trade)", config.BET_SIZE_PERCENT,
             config.get_bankroll() * config.BET_SIZE_PERCENT / 100)
    log.info("Poll interval: %ds", config.POLL_INTERVAL_SECONDS)

    # ── Initialize components ─────────────────────────────
    gamma = GammaClient()
    data = DataClient()
    clob = ClobClient()
    db = Storage()
    notifier = TelegramNotifier()

    guard_chain = GuardChain(clob, db)
    trade_engine = TradeEngine(clob, db, guard_chain, data_client=data)
    portfolio = PortfolioManager(clob, db, trade_engine.engine)
    scanner = LeaderboardScanner(data, gamma, db)
    monitor = TradeMonitor(data, gamma, db)

    # ── Signal handler for trade monitor ──────────────────
    def on_trade_signal(signal):
        try:
            position = trade_engine.process_signal(signal)
            if position:
                notifier.notify_trade_copied(signal, position)
            else:
                # Check if it was blocked
                passed, reason, _ = guard_chain.evaluate(signal)
                if not passed:
                    notifier.notify_trade_blocked(signal, reason)
        except Exception as e:
            log.error("Error processing signal: %s", e)
            notifier.notify_error(str(e))

    monitor.on_signal = on_trade_signal

    # ── Initial leaderboard scan ──────────────────────────
    log.info("Running initial leaderboard scan...")
    try:
        leaders = scanner.scan()
        notifier.notify_scan_complete(leaders)
    except Exception as e:
        log.error("Initial scan failed: %s", e)
        notifier.notify_error(f"Initial scan failed: {e}")

    # ── Background threads ────────────────────────────────

    # Thread 1: Trade monitor (polls leaders for new trades)
    def monitor_loop():
        log.info("Trade monitor thread started")
        monitor.start()

    # Thread 2: Portfolio manager (updates prices, checks stops)
    def portfolio_loop():
        log.info("Portfolio manager thread started")
        while not _shutdown.is_set():
            try:
                portfolio.update_cycle()
            except Exception as e:
                log.error("Portfolio update error: %s", e)
            _shutdown.wait(timeout=config.POLL_INTERVAL_SECONDS)

    # Thread 3: Periodic leaderboard rescan
    def scan_loop():
        log.info("Leaderboard scan thread started (every %dh)", config.SCAN_INTERVAL_HOURS)
        while not _shutdown.is_set():
            _shutdown.wait(timeout=config.SCAN_INTERVAL_HOURS * 3600)
            if _shutdown.is_set():
                break
            try:
                leaders = scanner.scan()
                notifier.notify_scan_complete(leaders)
            except Exception as e:
                log.error("Periodic scan failed: %s", e)
                notifier.notify_error(f"Scan failed: {e}")

    # Thread 4: Daily summary
    def summary_loop():
        log.info("Daily summary thread started")
        while not _shutdown.is_set():
            _shutdown.wait(timeout=86400)  # 24h
            if _shutdown.is_set():
                break
            try:
                summary = portfolio.get_portfolio_summary()
                notifier.notify_daily_summary(summary)
            except Exception as e:
                log.error("Summary failed: %s", e)

    threads = [
        threading.Thread(target=monitor_loop, daemon=True, name="monitor"),
        threading.Thread(target=portfolio_loop, daemon=True, name="portfolio"),
        threading.Thread(target=scan_loop, daemon=True, name="scanner"),
        threading.Thread(target=summary_loop, daemon=True, name="summary"),
    ]

    for t in threads:
        t.start()

    log.info("All threads started. Bot is running.")
    log.info("Press Ctrl+C to stop.")

    # ── Graceful shutdown ─────────────────────────────────
    def shutdown(signum, frame):
        log.info("Shutdown signal received...")
        _shutdown.set()
        monitor.stop()
        db.close()
        log.info("Shutdown complete.")
        sys.exit(0)

    sig.signal(sig.SIGINT, shutdown)
    sig.signal(sig.SIGTERM, shutdown)

    # Keep main thread alive
    while not _shutdown.is_set():
        _shutdown.wait(timeout=1)


if __name__ == "__main__":
    main()
