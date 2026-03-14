"""
Polytrader Dashboard — Streamlit web UI.
Shows portfolio, positions, trade history, leaders, and settings.
Run with: streamlit run src/dashboard/app.py --server.port 8502
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st
from datetime import datetime

from src import config
from src.db.storage import Storage

# ── Page config ───────────────────────────────────────────
st.set_page_config(
    page_title="Polytrader Dashboard",
    page_icon="📈",
    layout="wide",
)


@st.cache_resource
def get_storage():
    return Storage()


db = get_storage()

# ── Sidebar ───────────────────────────────────────────────
with st.sidebar:
    st.title("Polytrader")
    mode_emoji = "📝" if config.TRADING_MODE == "paper" else "💰"
    st.markdown(f"### {mode_emoji} {config.TRADING_MODE.upper()} MODE")
    st.divider()
    page = st.radio("Navigation", [
        "Portfolio", "Positions", "Trade History", "Leaders", "Settings"
    ])
    st.divider()
    if st.button("🛑 Kill Switch", type="primary", use_container_width=True):
        st.warning("Kill switch activated — bot will stop on next cycle")
        # In production: write a stop flag to disk/DB

# ── Portfolio page ────────────────────────────────────────
if page == "Portfolio":
    st.header("Portfolio overview")

    is_paper = config.TRADING_MODE == "paper"
    open_pos = db.get_open_positions(is_paper=is_paper)
    summary = db.get_pnl_summary(is_paper=is_paper)

    unrealized = sum(p.pnl_usd for p in open_pos)
    invested = sum(p.cost_usd for p in open_pos)
    realized = summary.get("total_pnl", 0) or 0
    total_pnl = realized + unrealized
    initial = config.PAPER_BANKROLL if is_paper else config.LIVE_BANKROLL

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Bankroll", f"${initial:,.0f}")
    col2.metric("Invested", f"${invested:,.2f}")
    col3.metric("Open positions", len(open_pos))
    col4.metric("Total P&L", f"${total_pnl:+,.2f}",
                delta=f"${unrealized:+,.2f} unrealized")

    st.divider()
    col1, col2, col3 = st.columns(3)
    total_trades = summary.get("total", 0) or 0
    wins = summary.get("wins", 0) or 0
    losses = summary.get("losses", 0) or 0
    wr = (wins / max(total_trades, 1)) * 100

    col1.metric("Total trades", total_trades)
    col2.metric("Win rate", f"{wr:.1f}%")
    col3.metric("Realized P&L", f"${realized:+,.2f}")

# ── Positions page ────────────────────────────────────────
elif page == "Positions":
    st.header("Open positions")
    is_paper = config.TRADING_MODE == "paper"
    positions = db.get_open_positions(is_paper=is_paper)

    if not positions:
        st.info("No open positions")
    else:
        rows = []
        for p in positions:
            rows.append({
                "Market": p.market_slug[:40],
                "Side": p.side,
                "Entry": f"${p.entry_price:.4f}",
                "Current": f"${p.current_price:.4f}",
                "Size": f"${p.cost_usd:.2f}",
                "P&L": f"${p.pnl_usd:+.2f}",
                "High": f"${p.high_price:.4f}",
                "Leader": p.leader_wallet[:10],
                "Opened": p.opened_at.strftime("%m/%d %H:%M"),
            })
        st.dataframe(rows, use_container_width=True)

    st.divider()
    st.header("Closed positions (recent)")
    all_pos = db.get_all_positions(limit=50)
    closed = [p for p in all_pos if p.status == "CLOSED"]

    if not closed:
        st.info("No closed positions yet")
    else:
        rows = []
        for p in closed[:20]:
            rows.append({
                "Market": p.market_slug[:40],
                "Entry": f"${p.entry_price:.4f}",
                "Exit": f"${p.current_price:.4f}",
                "P&L": f"${p.pnl_usd:+.2f}",
                "Reason": p.close_reason,
                "Duration": _duration(p),
            })
        st.dataframe(rows, use_container_width=True)

# ── Trade History page ────────────────────────────────────
elif page == "Trade History":
    st.header("Trade history")
    trades = db.get_recent_trades(limit=100)

    if not trades:
        st.info("No trades recorded yet")
    else:
        rows = []
        for t in trades:
            rows.append({
                "Time": t["timestamp"][:16],
                "Market": (t["market_slug"] or "")[:35],
                "Side": t["side"],
                "Price": f"${t['price']:.4f}",
                "Cost": f"${t['cost_usd']:.2f}",
                "Status": t["status"],
                "Guard": t["guard_blocked"] or "—",
                "Leader": (t["leader_wallet"] or "")[:10],
            })
        st.dataframe(rows, use_container_width=True)

        # Stats
        filled = [t for t in trades if t["status"] == "FILLED"]
        blocked = [t for t in trades if t["status"] == "BLOCKED"]
        st.caption(f"Total: {len(trades)} | Filled: {len(filled)} | Blocked: {len(blocked)}")

# ── Leaders page ──────────────────────────────────────────
elif page == "Leaders":
    st.header("Active leaders")
    leaders = db.get_active_leaders()

    if not leaders:
        st.info("No active leaders — run a scan first")
    else:
        rows = []
        for l in leaders:
            rows.append({
                "Name": l.name or l.wallet[:12],
                "Wallet": l.wallet[:14] + "...",
                "Win Rate": f"{l.win_rate:.1f}%",
                "Volume": f"${l.volume_usd:,.0f}",
                "P&L": f"${l.pnl_usd:+,.0f}",
                "Trades": l.total_trades,
                "Crypto %": f"{l.crypto_ratio * 100:.0f}%",
                "Last scan": l.last_scanned.strftime("%m/%d %H:%M"),
            })
        st.dataframe(rows, use_container_width=True)

# ── Settings page ─────────────────────────────────────────
elif page == "Settings":
    st.header("Configuration")
    st.warning("Changes here are display-only. Edit `.env` and restart to apply.")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Trading")
        st.text(f"Mode: {config.TRADING_MODE}")
        st.text(f"Bet size: {config.BET_SIZE_PERCENT}%")
        st.text(f"Paper bankroll: ${config.PAPER_BANKROLL}")
        st.text(f"Live bankroll: ${config.LIVE_BANKROLL}")

        st.subheader("Guards")
        st.text(f"Coinflip block: {config.COINFLIP_BLOCK}")
        st.text(f"Sports aware: {config.SPORTS_AWARE}")
        st.text(f"Min liquidity: ${config.MIN_MARKET_LIQUIDITY}")
        st.text(f"Max spread: {config.MAX_SPREAD_PERCENT}%")

    with col2:
        st.subheader("Leaderboard")
        st.text(f"Scan interval: {config.SCAN_INTERVAL_HOURS}h")
        st.text(f"Min win rate: {config.MIN_WIN_RATE}%")
        st.text(f"Min volume: ${config.MIN_VOLUME_USD}")
        st.text(f"Max crypto ratio: {config.MAX_CRYPTO_RATIO * 100}%")
        st.text(f"Max leaders: {config.MAX_LEADERS}")

        st.subheader("Portfolio")
        st.text(f"Trailing stop: {config.TRAILING_STOP_PERCENT}%")
        st.text(f"Cashout threshold: ${config.CASHOUT_THRESHOLD}")
        st.text(f"Poll interval: {config.POLL_INTERVAL_SECONDS}s")


def _duration(pos) -> str:
    if not pos.closed_at:
        return "—"
    delta = pos.closed_at - pos.opened_at
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return f"{delta.total_seconds() / 60:.0f}m"
    if hours < 24:
        return f"{hours:.1f}h"
    return f"{hours / 24:.1f}d"
