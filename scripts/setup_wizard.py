#!/usr/bin/env python3
"""
Setup Wizard — Interactive first-run configuration.
Generates the .env file from user input.
"""
import os
import sys
from pathlib import Path


def main():
    print("=" * 50)
    print("  POLYTRADER CLONE — Setup Wizard")
    print("=" * 50)
    print()

    env_path = Path(__file__).resolve().parent.parent / ".env"

    if env_path.exists():
        resp = input(".env already exists. Overwrite? [y/N]: ").strip().lower()
        if resp != "y":
            print("Setup cancelled.")
            return

    print("\n--- Trading Mode ---")
    print("  paper = simulate with virtual money (recommended to start)")
    print("  live  = real trades with real USDC")
    mode = input("Mode [paper]: ").strip().lower() or "paper"

    print("\n--- Wallet ---")
    if mode == "live":
        pk = input("Private key (hex): ").strip()
        proxy = input("Polymarket proxy wallet address: ").strip()
        sig_type = input("Signature type (1=email, 2=browser, 0=EOA) [1]: ").strip() or "1"
    else:
        pk = ""
        proxy = ""
        sig_type = "1"
        print("  Skipped (not needed for paper mode)")

    print("\n--- Bankroll ---")
    paper_bank = input("Paper bankroll [$1000]: ").strip() or "1000"
    live_bank = input("Live bankroll [$100]: ").strip() or "100"
    bet_pct = input("Bet size % per trade [5]: ").strip() or "5"

    print("\n--- Telegram Notifications (optional) ---")
    tg_token = input("Bot token (leave blank to skip): ").strip()
    tg_chat = input("Chat ID: ").strip() if tg_token else ""

    print("\n--- Leader Selection ---")
    min_wr = input("Min win rate % [55]: ").strip() or "55"
    min_vol = input("Min volume $ [5000]: ").strip() or "5000"
    max_leaders = input("Max leaders to follow [10]: ").strip() or "10"

    # Write .env
    lines = [
        f"TRADING_MODE={mode}",
        f"PRIVATE_KEY={pk}",
        f"POLYMARKET_PROXY_ADDRESS={proxy}",
        f"SIGNATURE_TYPE={sig_type}",
        f"PAPER_BANKROLL={paper_bank}",
        f"LIVE_BANKROLL={live_bank}",
        f"BET_SIZE_PERCENT={bet_pct}",
        f"TELEGRAM_BOT_TOKEN={tg_token}",
        f"TELEGRAM_CHAT_ID={tg_chat}",
        f"MIN_WIN_RATE={min_wr}",
        f"MIN_VOLUME_USD={min_vol}",
        f"MAX_LEADERS={max_leaders}",
        "SCAN_INTERVAL_HOURS=24",
        "POLL_INTERVAL_SECONDS=30",
        "COINFLIP_BLOCK=true",
        "SPORTS_AWARE=true",
        "MIN_MARKET_LIQUIDITY=5000",
        "MAX_SPREAD_PERCENT=10",
        "MIN_ODDS=0.05",
        "MAX_ODDS=0.95",
        "MAX_CRYPTO_RATIO=0.4",
        "TRAILING_STOP_PERCENT=15",
        "CASHOUT_THRESHOLD=0.98",
        "PROFIT_SKIM_PERCENT=0",
        "PROFIT_SKIM_WALLET=",
        "DASHBOARD_PORT=8502",
    ]

    env_path.write_text("\n".join(lines) + "\n")
    print(f"\n✓ .env written to {env_path}")
    print("\nNext steps:")
    print("  1. docker compose up -d")
    print("  2. Open http://localhost:8502 for the dashboard")
    print(f"  3. Bot starts in {mode.upper()} mode")


if __name__ == "__main__":
    main()
