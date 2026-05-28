"""
Standalone screener run: prints today's picks without doing anything else.

Usage:
    python scripts/run_screener.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from config.settings import MOMENTUM_LOOKBACK_DAYS, TOP_N, UNIVERSE
from src.data_pipeline.fetch_prices import load_universe
from src.screeners.momentum import MomentumScreener
from src.utils.logging import get_logger

log = get_logger(__name__)

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "data" / "screener_output.csv"


def main() -> None:
    log.info("Loading cached prices for %d tickers", len(UNIVERSE))
    prices = load_universe(UNIVERSE)

    screener = MomentumScreener(lookback=MOMENTUM_LOOKBACK_DAYS, top_n=TOP_N)
    picks = screener.screen(prices)

    if not picks:
        log.warning("No picks returned — all stocks filtered out.")
        return

    # Build a DataFrame for display and export
    rows = [
        {
            "rank": i + 1,
            "ticker": p.ticker,
            "score": round(p.score, 4),
            "reason": p.reason,
            "as_of": date.today().isoformat(),
        }
        for i, p in enumerate(picks)
    ]
    df = pd.DataFrame(rows)

    # Console table
    print("\n" + "=" * 60)
    print(f"  Momentum Picks — {date.today()}  (lookback={MOMENTUM_LOOKBACK_DAYS}d, top {TOP_N})")
    print("=" * 60)
    print(df[["rank", "ticker", "score", "reason"]].to_string(index=False))
    print("=" * 60 + "\n")

    # CSV output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    log.info("Results written to %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()
