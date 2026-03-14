"""
Polytrader Clone — Global Configuration
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _bool(val: str) -> bool:
    return val.lower() in ("true", "1", "yes")


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


# ── Mode ──────────────────────────────────────────────────
TRADING_MODE = os.getenv("TRADING_MODE", "paper")

# ── Wallet ────────────────────────────────────────────────
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "")
PROXY_ADDRESS = os.getenv("POLYMARKET_PROXY_ADDRESS", "")
SIGNATURE_TYPE = _int("SIGNATURE_TYPE", 1)

# ── Bankroll ──────────────────────────────────────────────
LIVE_BANKROLL = _float("LIVE_BANKROLL", 100.0)
PAPER_BANKROLL = _float("PAPER_BANKROLL", 1000.0)
BET_SIZE_PERCENT = _float("BET_SIZE_PERCENT", 5.0)

def get_bankroll() -> float:
    return PAPER_BANKROLL if TRADING_MODE == "paper" else LIVE_BANKROLL

# ── Telegram ──────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Leaderboard ───────────────────────────────────────────
SCAN_INTERVAL_HOURS = _int("SCAN_INTERVAL_HOURS", 24)
MIN_WIN_RATE = _float("MIN_WIN_RATE", 55.0)
MIN_VOLUME_USD = _float("MIN_VOLUME_USD", 5000.0)
MAX_CRYPTO_RATIO = _float("MAX_CRYPTO_RATIO", 0.4)
MAX_LEADERS = _int("MAX_LEADERS", 10)

# ── Monitor ───────────────────────────────────────────────
POLL_INTERVAL_SECONDS = _int("POLL_INTERVAL_SECONDS", 30)

# ── Guards ────────────────────────────────────────────────
COINFLIP_BLOCK = _bool(os.getenv("COINFLIP_BLOCK", "true"))
SPORTS_AWARE = _bool(os.getenv("SPORTS_AWARE", "true"))
MIN_MARKET_LIQUIDITY = _float("MIN_MARKET_LIQUIDITY", 5000.0)
MAX_SPREAD_PERCENT = _float("MAX_SPREAD_PERCENT", 10.0)
MIN_ODDS = _float("MIN_ODDS", 0.05)
MAX_ODDS = _float("MAX_ODDS", 0.95)

# ── Price Filter ──────────────────────────────────────
MIN_AVG_PRICE = _float("MIN_AVG_PRICE", 0.005)   # 0.5¢
MAX_AVG_PRICE = _float("MAX_AVG_PRICE", 0.40)    # 40¢
PRICE_FILTER_ENABLED = _bool(os.getenv("PRICE_FILTER_ENABLED", "true"))

# ── Whale Sizing ─────────────────────────────────────
WHALE_SIZING_ENABLED = _bool(os.getenv("WHALE_SIZING_ENABLED", "true"))
WHALE_SIZING_MAX_PCT = _float("WHALE_SIZING_MAX_PCT", 20.0)  # cap at 20% of bankroll

# ── Leader Scan Persistence ──────────────────────────
MIN_SCAN_COUNT = _int("MIN_SCAN_COUNT", 5)  # min consecutive scans to be trusted

# ── Portfolio ─────────────────────────────────────────────
TRAILING_STOP_PERCENT = _float("TRAILING_STOP_PERCENT", 15.0)
CASHOUT_THRESHOLD = _float("CASHOUT_THRESHOLD", 0.98)
PROFIT_SKIM_PERCENT = _float("PROFIT_SKIM_PERCENT", 0.0)
PROFIT_SKIM_WALLET = os.getenv("PROFIT_SKIM_WALLET", "")

# ── Dashboard ─────────────────────────────────────────────
DASHBOARD_PORT = _int("DASHBOARD_PORT", 8502)

# ── API URLs ──────────────────────────────────────────────
GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
CLOB_WSS = "wss://ws-subscriptions-clob.polymarket.com"

# ── Database ──────────────────────────────────────────────
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "polytrader.db"
