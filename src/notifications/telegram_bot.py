"""
Telegram Notifier — Sends real-time alerts to a Telegram chat.
Covers: new trades, position exits, errors, daily summaries.
"""
import logging
import requests
from datetime import datetime, timezone

from src import config
from src.models import Position, TradeSignal

log = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends formatted messages to a Telegram chat via Bot API."""

    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)
        if not self.enabled:
            log.warning("Telegram notifications disabled (missing token or chat_id)")

    def _send(self, text: str):
        """Send a message via Telegram Bot API."""
        if not self.enabled:
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            resp = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }, timeout=10)
            if resp.status_code != 200:
                log.warning("Telegram send failed: %s", resp.text[:100])
        except Exception as e:
            log.error("Telegram error: %s", e)

    # ── Trade alerts ──────────────────────────────────────

    def notify_trade_copied(self, signal: TradeSignal, position: Position):
        """Alert when a trade is successfully copied."""
        mode = "📝 PAPER" if position.is_paper else "💰 LIVE"
        self._send(
            f"{mode} <b>COPY TRADE</b>\n\n"
            f"🎯 <b>{signal.market.question[:60]}</b>\n"
            f"📊 Side: {signal.side}\n"
            f"💵 Size: ${position.cost_usd:.2f}\n"
            f"📈 Price: ${position.entry_price:.4f}\n"
            f"👤 Leader: {signal.leader.name or signal.leader.wallet[:10]}\n"
            f"🕐 {datetime.now(timezone.utc).strftime('%H:%M UTC')}"
        )

    def notify_trade_blocked(self, signal: TradeSignal, reason: str):
        """Alert when a trade is blocked by a guard."""
        self._send(
            f"🛡️ <b>TRADE BLOCKED</b>\n\n"
            f"Market: {signal.market.question[:60]}\n"
            f"Reason: <code>{reason}</code>\n"
            f"Leader: {signal.leader.name or signal.leader.wallet[:10]}"
        )

    # ── Exit alerts ───────────────────────────────────────

    def notify_position_closed(self, position: Position):
        """Alert when a position is closed."""
        emoji = "✅" if position.pnl_usd >= 0 else "❌"
        reason_map = {
            "trailing_stop": "📉 Trailing stop",
            "cashout": "💰 Instant cashout",
            "leader_exit": "🚪 Leader exit",
            "redemption": "🔗 On-chain redemption",
        }
        reason_text = reason_map.get(position.close_reason, position.close_reason)

        self._send(
            f"{emoji} <b>POSITION CLOSED</b>\n\n"
            f"Market: {position.market_slug[:40]}\n"
            f"Reason: {reason_text}\n"
            f"Entry: ${position.entry_price:.4f}\n"
            f"Exit: ${position.current_price:.4f}\n"
            f"P&L: <b>${position.pnl_usd:+.2f}</b>\n"
            f"Duration: {self._duration(position)}"
        )

    # ── Status / summary ──────────────────────────────────

    def notify_daily_summary(self, summary: dict):
        """Send end-of-day portfolio summary."""
        mode = "📝 PAPER" if summary.get("mode") == "paper" else "💰 LIVE"
        self._send(
            f"📊 <b>DAILY SUMMARY</b> {mode}\n\n"
            f"Open positions: {summary.get('open_positions', 0)}\n"
            f"Invested: ${summary.get('invested', 0):.2f}\n"
            f"Unrealized P&L: ${summary.get('unrealized_pnl', 0):+.2f}\n"
            f"Realized P&L: ${summary.get('realized_pnl', 0):+.2f}\n"
            f"<b>Total P&L: ${summary.get('total_pnl', 0):+.2f}</b>\n\n"
            f"Trades: {summary.get('total_trades', 0)} "
            f"(W: {summary.get('wins', 0)} / L: {summary.get('losses', 0)})\n"
            f"Win rate: {summary.get('win_rate', 0):.1f}%"
        )

    def notify_error(self, error_msg: str):
        """Alert on critical errors."""
        self._send(f"🚨 <b>ERROR</b>\n\n<code>{error_msg[:500]}</code>")

    def notify_scan_complete(self, leaders: list):
        """Alert when leaderboard scan completes."""
        leader_list = "\n".join(
            f"  • {l.name or l.wallet[:10]} — WR: {l.win_rate:.0f}%, PnL: ${l.pnl_usd:+.0f}"
            for l in leaders[:10]
        )
        self._send(
            f"🔍 <b>SCAN COMPLETE</b>\n\n"
            f"Leaders selected: {len(leaders)}\n\n"
            f"{leader_list}"
        )

    # ── Helpers ───────────────────────────────────────────

    def _duration(self, pos: Position) -> str:
        if not pos.closed_at:
            return "N/A"
        delta = pos.closed_at - pos.opened_at
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{delta.total_seconds() / 60:.0f}m"
        if hours < 24:
            return f"{hours:.1f}h"
        return f"{hours / 24:.1f}d"
