# Polytrader Clone

Copy-trading bot for Polymarket prediction markets. Discovers top-performing traders from the leaderboard and mirrors their trades automatically with 8 smart protections.

## Features

- **Leaderboard scanner** — Discovers top traders by win rate, volume, P&L (every 24h)
- **Trade monitor** — Polls leaders for new trades (~30s interval)
- **8 Smart protections** — Coinflip filter, sports-aware logic, market quality, leader quality, trailing stop-loss, instant cashout, on-chain redemption, event overlap prevention
- **Paper trading** — Simulates with real orderbook prices before going live
- **Live trading** — Maker orders for $0 entry fees via Polymarket CLOB
- **Dashboard** — Streamlit web UI with portfolio, positions, trades, settings
- **Telegram alerts** — Real-time notifications for trades, exits, errors, daily summaries

## Quick Start

### 1. Setup
```bash
git clone <repo-url> && cd polytrader-clone
python scripts/setup_wizard.py  # Interactive config → generates .env
```

### 2. Deploy
```bash
docker compose up -d
```
This starts both the bot and the dashboard.

### 3. Dashboard
Open `http://localhost:8502` in your browser.

## Manual Setup (without Docker)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your values
python scripts/test_api.py  # Verify API connectivity
python main.py  # Start the bot
```

Dashboard (separate terminal):
```bash
streamlit run src/dashboard/app.py --server.port 8502
```

## Configuration

All config lives in `.env`. Key parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `TRADING_MODE` | `paper` | `paper` or `live` |
| `PAPER_BANKROLL` | `1000` | Virtual bankroll for paper trading |
| `BET_SIZE_PERCENT` | `5` | % of bankroll per trade |
| `MIN_WIN_RATE` | `55` | Minimum leader win rate to follow |
| `MIN_VOLUME_USD` | `5000` | Minimum leader volume |
| `TRAILING_STOP_PERCENT` | `15` | Trailing stop-loss trigger |
| `CASHOUT_THRESHOLD` | `0.98` | Auto-sell when price hits this |
| `POLL_INTERVAL_SECONDS` | `30` | How often to check for new trades |

## Architecture

```
main.py                    ← Entry point, orchestrator
src/
├── config.py              ← All configuration from .env
├── models.py              ← Shared data models
├── api/
│   ├── gamma_client.py    ← Markets, events, tags (public)
│   ├── data_client.py     ← Leaderboard, activity, positions (public)
│   └── clob_client.py     ← Orderbook, prices, order placement (auth)
├── scanner/
│   ├── leaderboard.py     ← Discovers & filters top traders
│   └── trade_monitor.py   ← Polls leaders for new trades
├── guards/
│   ├── chain.py           ← Guard orchestrator
│   ├── coinflip_filter.py ← Blocks crypto speed markets
│   ├── sports_aware.py    ← Protects sports bets mid-game
│   ├── market_quality.py  ← Liquidity, spread, depth checks
│   └── leader_quality.py  ← Re-validates leader before copy
├── copier/
│   ├── trade_engine.py    ← Dispatcher (paper/live)
│   ├── paper_engine.py    ← Simulated execution
│   └── live_engine.py     ← Real CLOB execution
├── portfolio/
│   └── manager.py         ← Trailing stop, cashout, P&L
├── notifications/
│   └── telegram_bot.py    ← Telegram alerts
├── db/
│   └── storage.py         ← SQLite persistence
└── dashboard/
    └── app.py             ← Streamlit web UI
```

## Polymarket APIs Used

| API | Base URL | Auth | Purpose |
|-----|----------|------|---------|
| Gamma | `gamma-api.polymarket.com` | No | Market discovery, tags, metadata |
| Data | `data-api.polymarket.com` | No | Leaderboard, activity, positions |
| CLOB | `clob.polymarket.com` | For trading | Prices, orderbook, order placement |
| WSS | `ws-subscriptions-clob.polymarket.com` | No | Real-time price updates |

## Testing

```bash
python scripts/test_api.py   # API connectivity check
pytest tests/ -v             # Unit tests
```

## Disclaimer

Trading prediction markets involves substantial risk of financial loss. This software does not guarantee profits. Use paper mode first. Only trade with capital you can afford to lose. Not financial advice.
