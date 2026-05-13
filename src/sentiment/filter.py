"""
Combines news fetcher + FinBERT scorer into a trade gate.

Build:
  - SentimentFilter class
  - score(ticker) -> SentimentScore
  - allow_trade(ticker) -> bool

Important design choice: this is a ONE-WAY GATE.
  - We VETO trades when sentiment is strongly negative
  - We do NOT initiate trades just because sentiment is positive
  - Sentiment alone is too noisy to be a primary signal

If a ticker has no recent news, default to allowing the trade.
"""
