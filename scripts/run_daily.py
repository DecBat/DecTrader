"""
Full daily pipeline: data refresh -> screener -> sentiment filter -> paper orders.

Run this each morning before market open (e.g. 8:00 AM ET via Task Scheduler).
LM Studio must be running for sentiment to work — trades are BLOCKED if it is offline.

Usage:
    python scripts/run_daily.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from config.settings import (
    BACKTEST_START,
    BENCHMARK,
    MOMENTUM_LOOKBACK_DAYS,
    SENTIMENT_VETO_NEGATIVE,
    TOP_N,
    UNIVERSE,
)
from src.data_pipeline.fetch_prices import load_prices, load_universe, update_cache
from src.execution.alpaca_trader import AlpacaTrader
from src.screeners.momentum import MomentumScreener
from src.sentiment.filter import SentimentFilter
from src.utils.logging import get_logger

log = get_logger(__name__)

SMA_PERIOD = 200


def _spy_above_sma(spy_df: pd.DataFrame) -> bool:
    """Return True if SPY's latest close is above its 200-day SMA."""
    closes = spy_df["Close"].dropna()
    if len(closes) < SMA_PERIOD:
        log.warning("SPY has fewer than %d bars — trend filter skipped", SMA_PERIOD)
        return True
    sma = closes.iloc[-SMA_PERIOD:].mean()
    current = closes.iloc[-1]
    log.info(
        "SPY trend filter: close=%.2f  SMA200=%.2f  above_sma=%s",
        current, sma, current > sma,
    )
    return bool(current > sma)


def _print_summary(picks, approved_tickers: list[str], today: date) -> None:
    approved_set = set(approved_tickers)
    W = 60
    print(f"\n{'=' * W}")
    print(f"  Daily Pipeline  |  {today}")
    print(f"{'=' * W}")
    print(f"  {'Ticker':<8}  {'Score':>10}  Status")
    print(f"  {'-' * 32}")
    for pick in picks:
        status = "APPROVED" if pick.ticker in approved_set else "VETOED"
        print(f"  {pick.ticker:<8}  {pick.score:>10.4f}  {status}")
    print(f"{'=' * W}")
    print(f"  Submitting {len(approved_tickers)} tickers -> Alpaca: {approved_tickers}")
    print(f"{'=' * W}\n")


def main() -> None:
    today = date.today()
    log.info("=== run_daily start  %s ===", today)

    # Guard: skip weekends (Alpaca DAY orders on closed markets are rejected)
    if today.weekday() >= 5:
        log.info("Weekend — nothing to do")
        return

    # --- 1. Refresh price cache (incremental, only fetches new days) ---
    all_tickers = list(set(UNIVERSE) | {BENCHMARK})
    log.info("Refreshing price cache for %d tickers...", len(all_tickers))
    update_cache(all_tickers, start=BACKTEST_START)

    # --- 2. SPY trend filter ---
    try:
        spy_df = load_prices(BENCHMARK)
    except FileNotFoundError:
        log.error("SPY not cached after update — aborting")
        sys.exit(1)

    trader = AlpacaTrader()

    if not _spy_above_sma(spy_df):
        log.warning("SPY below 200d SMA — going to cash")
        trader.go_to_cash()
        log.info("=== run_daily done (cash mode) ===")
        return

    # --- 3. Momentum screener ---
    log.info("Loading prices and running momentum screener...")
    prices = load_universe(UNIVERSE)
    picks = MomentumScreener(lookback=MOMENTUM_LOOKBACK_DAYS, top_n=TOP_N).screen(prices)

    if not picks:
        log.warning("No momentum picks — going to cash")
        trader.go_to_cash()
        log.info("=== run_daily done (no picks) ===")
        return

    # --- 4. Sentiment filter (LM Studio) ---
    log.info("Running sentiment filter on %d picks...", len(picks))
    sentiment_filter = SentimentFilter(veto_threshold=SENTIMENT_VETO_NEGATIVE)
    approved: list[str] = []
    for pick in picks:
        allowed, _ = sentiment_filter.allow_trade(pick.ticker)
        if allowed:
            approved.append(pick.ticker)

    _print_summary(picks, approved, today)

    if not approved:
        log.warning("All picks vetoed by sentiment — going to cash")
        trader.go_to_cash()
        log.info("=== run_daily done (all vetoed) ===")
        return

    # --- 5. Rebalance ---
    summary = trader.account_summary()
    log.info("Account equity: $%.2f  cash: $%.2f", summary["equity"], summary["cash"])
    trader.rebalance(approved)

    log.info("=== run_daily done ===")


if __name__ == "__main__":
    main()
