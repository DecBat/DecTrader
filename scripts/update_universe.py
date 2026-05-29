"""
Fetch the current S&P 500 constituent list from Wikipedia and save it
to data/sp500_tickers.json.

Run this whenever you want to refresh the universe (S&P 500 changes ~20-30
tickers per year due to additions and deletions).

Usage:
    python scripts/update_universe.py

After running, call fetch_data.py to download price history for any new tickers.
"""
import json
import sys
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
import pandas as pd

from src.utils.logging import get_logger

log = get_logger(__name__)

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "sp500_tickers.json"
WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def fetch_sp500_tickers() -> list[str]:
    log.info("Fetching S&P 500 constituent list from Wikipedia...")
    resp = requests.get(WIKIPEDIA_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    resp.raise_for_status()

    df = pd.read_html(StringIO(resp.text))[0]

    # yfinance uses hyphens, Wikipedia uses dots (BRK.B -> BRK-B)
    tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
    log.info("Found %d tickers", len(tickers))
    return tickers


def main():
    tickers = fetch_sp500_tickers()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(tickers, f, indent=2)

    log.info("Saved to %s", OUTPUT_PATH)
    print(f"\nS&P 500 universe: {len(tickers)} tickers saved to {OUTPUT_PATH}")
    print(f"Next step: run fetch_data.py to download price history for all tickers.")
    estimate_mins = round(len(tickers) * 0.5 / 60)
    print(f"Estimated download time: ~{estimate_mins} minutes\n")


if __name__ == "__main__":
    main()
