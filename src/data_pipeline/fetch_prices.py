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
    """Download each ticker and write to data/prices/<TICKER>.parquet."""
    import datetime

    if end is None:
        end = datetime.date.today().isoformat()

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    for ticker in tickers:
        try:
            df = fetch_one(ticker, start, end)
            path = _CACHE_DIR / f"{ticker}.parquet"
            df.to_parquet(path)
            log.info("Cached %s  (%d rows) → %s", ticker, len(df), path)
        except Exception as exc:
            log.warning("Failed to fetch %s: %s", ticker, exc)


def load_prices(ticker: str) -> pd.DataFrame:
    """Load cached OHLCV for one ticker. Raises FileNotFoundError if not cached."""
    path = _CACHE_DIR / f"{ticker}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"No cache for {ticker}. Run update_cache() first.")
    return pd.read_parquet(path)


def load_universe(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Load cached OHLCV for every ticker in the list."""
    return {t: load_prices(t) for t in tickers}
