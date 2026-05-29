"""
Fetch and cache daily OHLCV from yfinance.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf

from src.utils.logging import get_logger

log = get_logger(__name__)

_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "prices"


def fetch_one(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Download OHLCV for a single ticker and return a clean DataFrame."""
    log.info("Fetching %s  %s → %s", ticker, start, end)
    raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)

    # yfinance ≥0.2 returns MultiIndex columns for a single ticker — flatten them
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    raw.index = pd.to_datetime(raw.index)
    raw.index.name = "date"
    return raw.sort_index()


def update_cache(tickers: list[str], start: str = "2020-01-01", end: str | None = None) -> None:
    """
    Download and cache OHLCV for each ticker.

    Incremental update: if a parquet file already exists, only fetch
    new trading days since the last cached date. On first run (no cache),
    downloads the full history from `start`.
    """
    import datetime

    if end is None:
        # Use yesterday — today's data is rarely finalized before market close
        end = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    new_count = 0
    updated_count = 0
    skipped_count = 0

    for ticker in tickers:
        path = _CACHE_DIR / f"{ticker}.parquet"
        try:
            if path.exists():
                existing = pd.read_parquet(path)
                first_cached = existing.index.min()
                last_cached  = existing.index.max()

                needs_backfill = pd.Timestamp(start) < first_cached
                needs_forward  = pd.Timestamp(end)   > last_cached

                if not needs_backfill and not needs_forward:
                    log.debug("%s already up to date (%s to %s)",
                              ticker, first_cached.date(), last_cached.date())
                    skipped_count += 1
                    continue

                frames = [existing]

                if needs_backfill:
                    backfill_end = (first_cached - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                    log.info("%s backfilling %s to %s", ticker, start, backfill_end)
                    older = fetch_one(ticker, start, backfill_end)
                    if not older.empty:
                        frames.insert(0, older)

                if needs_forward:
                    forward_start = (last_cached + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
                    newer = fetch_one(ticker, forward_start, end)
                    if not newer.empty:
                        frames.append(newer)

                df = pd.concat(frames).sort_index()
                df = df[~df.index.duplicated(keep="last")]
                df.to_parquet(path)
                log.info("%s updated: %d rows (%s to %s)",
                         ticker, len(df), df.index.min().date(), df.index.max().date())
                updated_count += 1

            else:
                df = fetch_one(ticker, start, end)
                df.to_parquet(path)
                log.info("%s full download (%d rows)", ticker, len(df))
                new_count += 1

        except Exception as exc:
            log.warning("Failed to update %s: %s", ticker, exc)

    log.info(
        "Cache update complete — %d new, %d updated, %d already current",
        new_count, updated_count, skipped_count,
    )


def load_prices(ticker: str) -> pd.DataFrame:
    """Load cached OHLCV for one ticker. Raises FileNotFoundError if not cached."""
    path = _CACHE_DIR / f"{ticker}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No cache for {ticker}. Run update_cache() first.")
    return pd.read_parquet(path)


def load_universe(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Load cached OHLCV for every ticker in the list."""
    return {t: load_prices(t) for t in tickers}
