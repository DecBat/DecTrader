"""
Mean reversion screener.

Idea: stocks far below their N-day mean tend to bounce. Opposite of momentum.

Sketch:
  - For each ticker, compute z-score of current price vs N-day mean/std
  - Return tickers where z < threshold (e.g. -2.0), most-oversold first
  - Risk warning: in strong downtrends, 'oversold' can keep falling

Implement this AFTER momentum is working - it's useful for comparing
which style fits the current market regime.
"""
