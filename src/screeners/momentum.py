"""
Momentum screener — Clenow / Teddy Koker quality-momentum approach.

Score = annualized_slope * R²  computed over a log-price regression.
Stocks with negative momentum or fewer data points than the lookback are dropped.
The most-recent SKIP_DAYS are excluded to avoid the short-term reversal effect.

Reference:
  https://teddykoker.com/2019/05/momentum-strategy-from-stocks-on-the-move-in-python/
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.screeners.base import BaseScreener, ScreenerPick
from src.utils.logging import get_logger

log = get_logger(__name__)

SKIP_DAYS = 21  # skip the most recent ~1 month


def _momentum_score(close: pd.Series, lookback: int) -> tuple[float, float]:
    """
    Fit OLS on log(close) over `lookback` days (excluding the last SKIP_DAYS).
    Returns (annualized_slope, r_squared).
    """
    series = close.iloc[-(lookback + SKIP_DAYS): -SKIP_DAYS] if SKIP_DAYS else close.iloc[-lookback:]

    if len(series) < lookback * 0.8:
        return float("nan"), float("nan")

    x = np.arange(len(series))
    y = np.log(series.values.astype(float))

    # OLS via numpy
    slope, intercept = np.polyfit(x, y, 1)

    # R² — how well the log-linear trend fits
    y_hat = slope * x + intercept
    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    # Annualize the daily log-slope (252 trading days)
    annualized_slope = (np.exp(slope) ** 252) - 1

    return annualized_slope, r2


class MomentumScreener(BaseScreener):
    def __init__(self, lookback: int = 90, top_n: int = 5):
        self.lookback = lookback
        self.top_n = top_n

    def screen(self, prices: dict[str, pd.DataFrame]) -> list[ScreenerPick]:
        results: list[ScreenerPick] = []

        for ticker, df in prices.items():
            if "Close" not in df.columns or len(df) < self.lookback + SKIP_DAYS:
                log.debug("Skipping %s — insufficient data", ticker)
                continue

            slope, r2 = _momentum_score(df["Close"], self.lookback)

            if np.isnan(slope) or np.isnan(r2):
                log.debug("Skipping %s — could not compute score", ticker)
                continue

            score = slope * r2

            if score <= 0:
                log.debug("Skipping %s — negative momentum (score=%.4f)", ticker, score)
                continue

            results.append(ScreenerPick(
                ticker=ticker,
                score=round(score, 6),
                reason=f"annualized_slope={slope:.2%}  R²={r2:.3f}  score={score:.4f}",
            ))

        results.sort(key=lambda p: p.score, reverse=True)
        picks = results[: self.top_n]

        log.info(
            "Momentum screen: %d/%d passed, top %d: %s",
            len(results), len(prices), len(picks),
            [p.ticker for p in picks],
        )
        return picks
