"""
Standalone screener run: prints today's momentum picks with sentiment overlay.

Usage:
    python scripts/run_screener.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from config.settings import MOMENTUM_LOOKBACK_DAYS, SENTIMENT_VETO_NEGATIVE, TOP_N, UNIVERSE
from src.data_pipeline.fetch_prices import load_universe
from src.screeners.momentum import MomentumScreener
from src.sentiment.filter import SentimentFilter
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

    log.info("Running sentiment filter on %d picks...", len(picks))
    sentiment_filter = SentimentFilter(veto_threshold=SENTIMENT_VETO_NEGATIVE)

    rows = []
    for i, pick in enumerate(picks):
        allowed, sent = sentiment_filter.allow_trade(pick.ticker)
        rows.append({
            "rank":      i + 1,
            "ticker":    pick.ticker,
            "mom_score": round(pick.score, 4),
            "P_pos":     round(sent.positive, 3),
            "P_neg":     round(sent.negative, 3),
            "P_neu":     round(sent.neutral,  3),
            "news_n":    sent.n_items,
            "vetoed":    not allowed,
            "as_of":     date.today().isoformat(),
        })

    df = pd.DataFrame(rows)

    passed  = df[~df["vetoed"]]
    vetoed  = df[ df["vetoed"]]

    W = 72
    print("\n" + "=" * W)
    print(f"  Momentum + Sentiment Picks  |  {date.today()}  (lookback={MOMENTUM_LOOKBACK_DAYS}d, top {TOP_N})")
    print(f"  Sentiment veto threshold: P(negative) > {SENTIMENT_VETO_NEGATIVE}")
    print("=" * W)

    if not passed.empty:
        print("\n  APPROVED PICKS")
        print(
            passed[["rank", "ticker", "mom_score", "P_pos", "P_neg", "P_neu", "news_n"]]
            .to_string(index=False)
        )

    if not vetoed.empty:
        print("\n  VETOED BY SENTIMENT")
        print(
            vetoed[["rank", "ticker", "mom_score", "P_pos", "P_neg", "P_neu", "news_n"]]
            .to_string(index=False)
        )

    print("\n" + "=" * W + "\n")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    log.info("Results written to %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()
