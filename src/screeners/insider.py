"""
Insider trading screener — scans the full universe for significant open-market
purchases by corporate insiders (SEC Form 4) and returns the highest-conviction
picks as ScreenerPick objects.

Designed to run as a PARALLEL signal alongside MomentumScreener, not as a
filter on top of it. Insider buying is most valuable when a stock is NOT yet
in a strong uptrend — exactly the situation where momentum screening misses it.

Scoring
-------
For each ticker:
  base_score = sum of (dollar_value × recency_weight) for open-market purchases
  cluster_multiplier = 1.5 if 2+ unique insiders bought in any 30-day window

Recency weights:
  0-7 days   : 1.0
  8-30 days  : 0.8
  31-60 days : 0.5

Only open-market purchases (transactionCode="P") count toward the score.
Sales are ignored — insiders sell for too many non-predictive reasons.

Parallelisation
---------------
SEC EDGAR requests are I/O-bound. We use a ThreadPoolExecutor with
_MAX_WORKERS concurrent threads. Each thread rate-limits its own requests
at _REQUEST_INTERVAL seconds, keeping total throughput well under SEC's
10 req/sec ceiling. 10 workers × (1 / ~2s per request) = ~5 req/sec.
Expected runtime: ~7 minutes for 500 tickers.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd

from src.data_pipeline.fetch_insider import fetch_insider_transactions
from src.screeners.base import BaseScreener, ScreenerPick
from src.utils.logging import get_logger

log = get_logger(__name__)

# --- Scoring constants ---
_RECENCY_WEIGHTS: list[tuple[int, float]] = [
    (7,  1.0),   # purchased in last week     -> full weight
    (30, 0.8),   # purchased in last month    -> 80%
    (60, 0.5),   # purchased in last 2 months -> 50%
]
_CLUSTER_DAYS       = 30
_CLUSTER_MIN        = 2
_CLUSTER_MULTIPLIER = 1.5
_MIN_SCORE          = 50_000   # minimum weighted buy value to appear as a pick
_MAX_WORKERS        = 10       # concurrent EDGAR threads
_LOG_EVERY          = 50       # log progress every N completed tickers


def _recency_weight(txn_date: date, today: date) -> float:
    age = (today - txn_date).days
    for days, weight in _RECENCY_WEIGHTS:
        if age <= days:
            return weight
    return 0.0


def _has_cluster(buys: list[dict]) -> bool:
    """Return True if 2+ unique insiders bought within any _CLUSTER_DAYS window."""
    entries: list[tuple[date, str]] = []
    for t in buys:
        try:
            entries.append((date.fromisoformat(t["transactionDate"]), t.get("name", "")))
        except (KeyError, ValueError):
            continue

    entries.sort()
    window = timedelta(days=_CLUSTER_DAYS)
    for i, (d_start, _) in enumerate(entries):
        buyers = {name for d, name in entries[i:] if d <= d_start + window}
        if len(buyers) >= _CLUSTER_MIN:
            return True
    return False


def _score_ticker(ticker: str, days: int) -> tuple[str, float, str]:
    """
    Fetch and score insider activity for one ticker.
    Returns (ticker, score, reason). Score is 0.0 if no qualifying purchases.
    """
    today        = date.today()
    transactions = fetch_insider_transactions(ticker, days)
    buys         = [t for t in transactions if t.get("transactionCode") == "P"]

    if not buys:
        return ticker, 0.0, ""

    weighted_total = 0.0
    n_buyers: set[str] = set()

    for t in buys:
        try:
            txn_date = date.fromisoformat(t["transactionDate"])
        except (KeyError, ValueError):
            continue

        w = _recency_weight(txn_date, today)
        if w == 0.0:
            continue

        shares = abs(t.get("share", 0) or 0)
        price  = abs(t.get("transactionPrice", 0) or 0)
        weighted_total += shares * price * w
        n_buyers.add(t.get("name", "unknown"))

    if weighted_total < _MIN_SCORE:
        return ticker, 0.0, ""

    cluster = _has_cluster(buys)
    if cluster:
        weighted_total *= _CLUSTER_MULTIPLIER

    reason = (
        f"insider_buy=${weighted_total:,.0f}  buyers={len(n_buyers)}"
        + ("  CLUSTER" if cluster else "")
    )
    return ticker, round(weighted_total, 2), reason


class InsiderScreener(BaseScreener):
    """
    Scans the full universe for insider buying conviction and returns the
    highest-scoring tickers as ScreenerPick objects.

    Does NOT require price data — accepts the same prices dict as
    MomentumScreener (for interface compatibility) but only uses the keys.
    """

    def __init__(self, top_n: int = 3, days: int = 60):
        self.top_n = top_n
        self.days  = days

    def screen(self, prices: dict[str, pd.DataFrame]) -> list[ScreenerPick]:
        tickers = list(prices.keys())
        total   = len(tickers)
        scores: dict[str, tuple[float, str]] = {}

        est_minutes = (total * 1.5) / _MAX_WORKERS / 60
        log.info(
            "Insider scan: %d tickers  lookback=%dd  workers=%d  (~%.0f min)",
            total, self.days, _MAX_WORKERS, est_minutes,
        )

        completed = 0
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futures = {
                pool.submit(_score_ticker, ticker, self.days): ticker
                for ticker in tickers
            }
            for future in as_completed(futures):
                try:
                    ticker, score, reason = future.result()
                    if score >= _MIN_SCORE:
                        scores[ticker] = (score, reason)
                except Exception as exc:
                    log.warning("Insider score error for %s: %s", futures[future], exc)

                completed += 1
                if completed % _LOG_EVERY == 0 or completed == total:
                    log.info(
                        "Insider scan progress: %d/%d  (%d candidates so far)",
                        completed, total, len(scores),
                    )

        ranked = sorted(scores, key=lambda t: scores[t][0], reverse=True)[: self.top_n]
        picks  = [
            ScreenerPick(ticker=t, score=scores[t][0], reason=scores[t][1])
            for t in ranked
        ]

        log.info(
            "Insider screen: %d/%d tickers had qualifying purchases, top %d: %s",
            len(scores), total, len(picks),
            [p.ticker for p in picks],
        )
        return picks
