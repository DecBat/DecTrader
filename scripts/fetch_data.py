"""
Refresh local price cache for the configured universe.

Usage:
    python scripts/fetch_data.py
"""
import sys
from pathlib import Path

# Allow imports from the project root when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import BACKTEST_START, UNIVERSE
from src.data_pipeline.fetch_prices import update_cache
from src.utils.logging import get_logger

log = get_logger(__name__)

if __name__ == "__main__":
    log.info("Starting price cache refresh for %d tickers", len(UNIVERSE))
    update_cache(UNIVERSE, start=BACKTEST_START)
    log.info("Done.")
