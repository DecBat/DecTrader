"""
Fetch and cache daily OHLCV from yfinance.

Functions to build:
  - fetch_one(ticker, start, end) -> DataFrame
  - update_cache(tickers) -> writes parquet files to data/prices/
  - load_prices(ticker) -> DataFrame
  - load_universe(tickers) -> dict[ticker, DataFrame]

Notes:
  - Use auto_adjust=True for split/dividend adjustment
  - yfinance returns MultiIndex columns for single tickers in newer versions - flatten them
  - Cache as parquet (faster than CSV, preserves dtypes)
"""
