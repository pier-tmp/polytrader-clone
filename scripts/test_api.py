#!/usr/bin/env python3
"""
API Test — Validates connectivity to all Polymarket APIs.
Run before deploying to ensure everything works.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api.gamma_client import GammaClient
from src.api.data_client import DataClient
from src.api.clob_client import ClobClient


def test_gamma():
    print("\n--- Gamma API ---")
    gamma = GammaClient()

    markets = gamma.get_markets(limit=3)
    print(f"  Markets: {len(markets)} fetched")
    if markets:
        m = markets[0]
        print(f"  First: {m.get('question', 'N/A')[:60]}")
        print(f"  Tags: {gamma.get_market_tags(m.get('conditionId', ''))}")
        print(f"  Crypto: {gamma.is_crypto_market(m)}")
        print(f"  Sports: {gamma.is_sports_market(m)}")
    return bool(markets)


def test_data():
    print("\n--- Data API ---")
    data = DataClient()

    lb = data.get_leaderboard(limit=3)
    print(f"  Leaderboard: {len(lb)} entries")
    if lb:
        top = lb[0]
        wallet = top.get("userAddress", top.get("proxyWallet", ""))
        pnl = top.get("pnl", top.get("profit", 0))
        print(f"  Top: {wallet[:12]}... PnL: ${float(pnl):+,.0f}")

        activity = data.get_activity(wallet, limit=3)
        print(f"  Activity: {len(activity)} trades")

        positions = data.get_positions(wallet, limit=3)
        print(f"  Positions: {len(positions)} open")
    return bool(lb)


def test_clob():
    print("\n--- CLOB API ---")
    clob = ClobClient()

    # Need a token_id to test. Get from Gamma first.
    gamma = GammaClient()
    markets = gamma.get_markets(limit=1)
    if not markets:
        print("  ✗ No markets to test with")
        return False

    m = markets[0]
    tokens = m.get("clobTokenIds", "")
    if isinstance(tokens, str):
        try:
            tokens = json.loads(tokens)
        except (json.JSONDecodeError, TypeError):
            tokens = [t.strip() for t in tokens.split(",") if t.strip()]
    if not isinstance(tokens, list):
        tokens = []

    if not tokens:
        print(f"  ✗ No token IDs found for {m.get('question', '')[:40]}")
        return False

    token_id = tokens[0]
    print(f"  Token: {token_id[:16]}...")

    mid = clob.get_midpoint(token_id)
    print(f"  Midpoint: ${mid:.4f}")

    price = clob.get_price(token_id, "BUY")
    print(f"  BUY price: ${price:.4f}")

    book = clob.get_order_book(token_id)
    bids = len(book.get("bids", []))
    asks = len(book.get("asks", []))
    print(f"  Orderbook: {bids} bids, {asks} asks")

    depth = clob.get_book_depth(token_id, "BUY")
    print(f"  BUY depth: ${depth:,.2f}")

    fill = clob.estimate_fill_price(token_id, "BUY", 50)
    print(f"  Est. fill for $50: ${fill:.4f}")

    return mid > 0


def main():
    print("=" * 50)
    print("  POLYTRADER — API Connection Test")
    print("=" * 50)

    results = {
        "Gamma API": test_gamma(),
        "Data API": test_data(),
        "CLOB API": test_clob(),
    }

    print("\n" + "=" * 50)
    print("  RESULTS")
    print("=" * 50)
    all_ok = True
    for name, ok in results.items():
        status = "✓ OK" if ok else "✗ FAILED"
        print(f"  {name}: {status}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\n  All APIs working! Ready to deploy.")
    else:
        print("\n  Some APIs failed. Check network and try again.")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
