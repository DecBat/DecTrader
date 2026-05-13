"""
Fetch recent news headlines for a ticker.

Default backend: Finnhub (free tier, ~1 year of company news history)
Endpoint: https://finnhub.io/api/v1/company-news

Function to build:
  fetch_news(ticker, lookback_days) -> list[dict]

Each dict should have at minimum: headline, summary, datetime, source, url.
Keep the return shape stable - the sentiment scorer depends on it.

Alternative backends to consider:
  - NewsAPI (broader sources but lower free-tier quota)
  - Alpaca News API (built into your broker)
  - SEC EDGAR for filings (free, official)
"""
