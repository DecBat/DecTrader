"""
Base class defining the screener contract.

Define:
  - ScreenerPick dataclass with fields: ticker, score, reason
  - BaseScreener ABC with one abstract method: screen(prices) -> list[ScreenerPick]

All screeners take a dict of {ticker: price_dataframe} and return picks
sorted by score descending (best first).
"""
