"""
Fetch recent news headlines for a ticker via Finnhub.
"""
from __future__ import annotations

from datetime import date, timedelta

import requests

from config.settings import FINNHUB_API_KEY
from src.utils.logging import get_logger

log = get_logger(__name__)

_FINNHUB_URL = "https://finnhub.io/api/v1/company-news"


def fetch_news(ticker: str, lookback_days: int = 7) -> list[dict]:
    """
    Return recent news articles for ticker from Finnhub.
    Each item has: headline, summary, datetime, source, url.
    Returns [] if no API key is configured or the request fails.
    """
    if not FINNHUB_API_KEY:
        log.warning("FINNHUB_API_KEY not set — skipping news fetch for %s", ticker)
        return []

    end = date.today()
    start = end - timedelta(days=lookback_days)

    try:
        resp = requests.get(
            _FINNHUB_URL,
            params={
                "symbol": ticker,
                "from": start.isoformat(),
                "to": end.isoformat(),
                "token": FINNHUB_API_KEY,
            },
            timeout=20,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Finnhub request failed for %s: %s", ticker, exc)
        return []

    articles = []
    for item in resp.json():
        headline = item.get("headline", "").strip()
        summary  = item.get("summary", "").strip()
        if not headline:
            continue
        articles.append({
            "headline": headline,
            "summary":  summary,
            "datetime": item.get("datetime", 0),
            "source":   item.get("source", ""),
            "url":      item.get("url", ""),
        })

    log.info("Fetched %d articles for %s (last %d days)", len(articles), ticker, lookback_days)
    return articles
