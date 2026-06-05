"""
Full daily pipeline:
    data refresh -> momentum screen -> insider screen -> combine -> sentiment -> orders

Run this each morning before market open (e.g. 8:00 AM ET via Task Scheduler).
LM Studio must be running for sentiment to work — falls back to neutral if offline.
Insider scan takes ~8-9 min for 500 tickers (Finnhub rate limit). Total runtime
before market open is ~20 min from an 8:00 AM start.

Usage:
    python scripts/run_daily.py
"""
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from config.settings import (
    BACKTEST_START,
    BENCHMARK,
    INSIDER_LOOKBACK_DAYS,
    MOMENTUM_LOOKBACK_DAYS,
    SENTIMENT_VETO_NEGATIVE,
    TOP_N,
    TOP_N_INSIDER,
    UNIVERSE,
)
from src.data_pipeline.fetch_prices import load_prices, load_universe, update_cache
from src.execution.alpaca_trader import AlpacaTrader
from src.screeners.insider import InsiderScreener
from src.screeners.momentum import MomentumScreener
from src.screeners.base import ScreenerPick
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
    sma     = closes.iloc[-SMA_PERIOD:].mean()
    current = closes.iloc[-1]
    log.info(
        "SPY trend filter: close=%.2f  SMA200=%.2f  above_sma=%s",
        current, sma, current > sma,
    )
    return bool(current > sma)


def _combine_picks(
    momentum_picks: list[ScreenerPick],
    insider_picks:  list[ScreenerPick],
) -> list[ScreenerPick]:
    """
    Merge both screeners' picks, deduplicating by ticker.
    If a ticker appears in both lists it keeps its momentum score (primary rank)
    but its source is noted as BOTH in the reason field.
    Result is sorted momentum picks first, then insider-only picks.
    """
    momentum_tickers = {p.ticker for p in momentum_picks}
    insider_tickers  = {p.ticker for p in insider_picks}
    both             = momentum_tickers & insider_tickers

    # Tag each pick with its source
    tagged: list[ScreenerPick] = []
    for p in momentum_picks:
        source = "MOMENTUM+INSIDER" if p.ticker in both else "MOMENTUM"
        tagged.append(ScreenerPick(ticker=p.ticker, score=p.score,
                                   reason=f"[{source}] {p.reason}"))

    for p in insider_picks:
        if p.ticker not in momentum_tickers:   # already included above
            tagged.append(ScreenerPick(ticker=p.ticker, score=p.score,
                                       reason=f"[INSIDER] {p.reason}"))

    return tagged


def _print_summary(
    picks:             list[ScreenerPick],
    sentiment_vetoed:  set[str],
    approved_tickers:  list[str],
    today:             date,
) -> None:
    approved_set = set(approved_tickers)
    W = 80
    print(f"\n{'=' * W}")
    print(f"  Daily Pipeline  |  {today}")
    print(f"{'=' * W}")
    print(f"  {'Ticker':<8}  {'Score':>12}  {'Source':<18}  {'Sentiment':<10}  Final")
    print(f"  {'-' * 64}")
    for pick in picks:
        # Extract source tag from reason prefix
        source = pick.reason.split("]")[0].lstrip("[") if pick.reason.startswith("[") else "UNKNOWN"
        sentiment_s = "VETOED" if pick.ticker in sentiment_vetoed else "OK"
        final       = "APPROVED" if pick.ticker in approved_set   else "VETOED"
        print(
            f"  {pick.ticker:<8}  {pick.score:>12.2f}  "
            f"{source:<18}  {sentiment_s:<10}  {final}"
        )
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

    # --- 3. Load prices for screeners ---
    log.info("Loading prices for screeners...")
    prices = load_universe(UNIVERSE)

    # --- 4. Momentum screener ---
    log.info("Running momentum screener...")
    momentum_picks = MomentumScreener(
        lookback=MOMENTUM_LOOKBACK_DAYS, top_n=TOP_N
    ).screen(prices)

    # --- 5. Insider screener (scans full universe via Finnhub Form 4 data) ---
    log.info("Running insider screener (~8 min for full universe)...")
    insider_picks = InsiderScreener(
        top_n=TOP_N_INSIDER, days=INSIDER_LOOKBACK_DAYS
    ).screen(prices)

    # --- 6. Combine both screeners' picks ---
    picks = _combine_picks(momentum_picks, insider_picks)

    if not picks:
        log.warning("No picks from either screener — going to cash")
        trader.go_to_cash()
        log.info("=== run_daily done (no picks) ===")
        return

    log.info(
        "Combined pool: %d picks  (%d momentum, %d insider, %d overlap)",
        len(picks),
        len(momentum_picks),
        len(insider_picks),
        len({p.ticker for p in momentum_picks} & {p.ticker for p in insider_picks}),
    )

    # Brief pause so Finnhub rate-limit window resets after the insider scan
    time.sleep(15)

    # --- 7. Sentiment filter (LM Studio) ---
    log.info("Running sentiment filter on %d picks...", len(picks))
    sentiment_filter  = SentimentFilter(veto_threshold=SENTIMENT_VETO_NEGATIVE)
    sentiment_vetoed: set[str] = set()
    approved: list[str] = []

    for pick in picks:
        allowed, _ = sentiment_filter.allow_trade(pick.ticker)
        if allowed:
            approved.append(pick.ticker)
        else:
            sentiment_vetoed.add(pick.ticker)

    _print_summary(picks, sentiment_vetoed, approved, today)

    if not approved:
        log.warning("All picks vetoed by sentiment — going to cash")
        trader.go_to_cash()
        log.info("=== run_daily done (all vetoed) ===")
        return

    # --- 8. Rebalance ---
    summary = trader.account_summary()
    log.info("Account equity: $%.2f  cash: $%.2f", summary["equity"], summary["cash"])
    trader.rebalance(approved)

    log.info("=== run_daily done ===")


if __name__ == "__main__":
    main()
