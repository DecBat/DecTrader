"""
Momentum screener.

Rank stocks by trailing return over a lookback window, optionally skipping
the most recent ~1 month to avoid the short-term reversal effect.

Two versions worth implementing in order:
  1. Simple: return = price_today / price_lookback - 1
  2. Quality momentum (Clenow): annualized regression slope * R^2 over lookback

See:
  https://teddykoker.com/2019/05/momentum-strategy-from-stocks-on-the-move-in-python/

Return top N picks with positive momentum, sorted descending.
"""
