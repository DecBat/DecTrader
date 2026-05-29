"""
Smoke test: confirms .env keys work and you can reach the Alpaca paper endpoint.

Usage:
    python scripts/check_alpaca_connection.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.execution.alpaca_trader import AlpacaTrader
from src.utils.logging import get_logger

log = get_logger(__name__)


def main():
    print("\nConnecting to Alpaca paper trading...")

    try:
        trader = AlpacaTrader()
    except RuntimeError as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)

    # Account summary
    summary = trader.account_summary()
    print("\n--- Account ---")
    print(f"  Equity:        ${summary['equity']:>12,.2f}")
    print(f"  Cash:          ${summary['cash']:>12,.2f}")
    print(f"  Buying power:  ${summary['buying_power']:>12,.2f}")

    # Current positions
    positions = trader.get_positions()
    print(f"\n--- Positions ({len(positions)} open) ---")
    if positions:
        for symbol, market_value in sorted(positions.items()):
            print(f"  {symbol:<8}  ${market_value:>10,.2f}")
    else:
        print("  No open positions")

    print("\nConnection OK\n")


if __name__ == "__main__":
    main()
