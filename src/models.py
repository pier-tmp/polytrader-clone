"""
Polytrader Clone — Shared Data Models
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Leader:
    wallet: str
    name: str = ""
    win_rate: float = 0.0
    volume_usd: float = 0.0
    pnl_usd: float = 0.0
    total_trades: int = 0
    crypto_ratio: float = 0.0
    last_scanned: datetime = field(default_factory=_utcnow)
    active: bool = True


@dataclass
class Market:
    condition_id: str
    token_id: str
    question: str = ""
    slug: str = ""
    tags: list = field(default_factory=list)
    end_date: Optional[datetime] = None
    volume_24h: float = 0.0
    liquidity: float = 0.0
    outcome: str = ""  # "Yes" / "No"


@dataclass
class TradeSignal:
    leader: Leader
    market: Market
    side: str  # "BUY" / "SELL"
    token_id: str = ""
    size_usd: float = 0.0
    price: float = 0.0
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass
class Position:
    id: Optional[int] = None
    market_slug: str = ""
    token_id: str = ""
    side: str = ""
    entry_price: float = 0.0
    size: float = 0.0           # in shares
    cost_usd: float = 0.0
    current_price: float = 0.0
    high_price: float = 0.0     # for trailing stop
    pnl_usd: float = 0.0
    leader_wallet: str = ""
    opened_at: datetime = field(default_factory=_utcnow)
    closed_at: Optional[datetime] = None
    close_reason: str = ""      # "trailing_stop", "cashout", "leader_exit", "redemption"
    is_paper: bool = True
    status: str = "OPEN"        # "OPEN" / "CLOSED"

    def update_pnl(self, current_price: float):
        self.current_price = current_price
        if current_price > self.high_price:
            self.high_price = current_price
        self.pnl_usd = (current_price - self.entry_price) * self.size


@dataclass
class TradeRecord:
    id: Optional[int] = None
    market_slug: str = ""
    token_id: str = ""
    side: str = ""
    price: float = 0.0
    size: float = 0.0
    cost_usd: float = 0.0
    leader_wallet: str = ""
    is_paper: bool = True
    timestamp: datetime = field(default_factory=_utcnow)
    order_id: str = ""
    status: str = "FILLED"      # "FILLED" / "REJECTED" / "PARTIAL"
    guard_blocked: str = ""     # which guard blocked it, empty if passed
