"""
Backtrader strategy class for momentum.

This is where the real validation work happens - backtests tell you whether
your screener has any edge before you risk paper (or real) capital.

Build:
  - MomentumIndicator (bt.Indicator): Clenow-style momentum
    (annualized regression slope * R^2 over lookback)
  - MomentumStrategy (bt.Strategy):
    * Weekly or monthly rebalance
    * Trend filter on benchmark (only go long when SPY > 200d SMA)
    * Equal-weight top N picks
    * Track positions with ATR-based stops

Output metrics to check: total return vs SPY, max drawdown, Sharpe,
win rate, average win/loss.

References:
  https://www.backtrader.com/docu/quickstart/quickstart/
  https://teddykoker.com/2019/05/momentum-strategy-from-stocks-on-the-move-in-python/
"""
