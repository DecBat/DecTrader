"""
Fetch SEC Form 4 insider transactions from Finnhub.

Only open-market purchases (code "P") and sales (code "S") are returned.
Grants, gifts, tax-withholding, and option exercises are excluded because
they carry no informational signal about management's price expectations.

Free-tier Finnhub key is sufficient — insider transactions are included.
"""
from __future__ import annotations

from datetime import date, timedelta

import requests

from config.settings import FINNHUB_API_KEY
from src.utils.logging import get_logger

log = get_logger(__name__)

_BASE    = "https://finnhub.io/api/v1"
_TIMEOUT = 10  # seconds

# Only these codes carry genuine buy/sell signal
_SIGNAL_CODES = {"P", "S"}  # P = open-market purchase, S = open-market sale


def fetch_insider_transactions(ticker: str, days: int = 90) -> list[dict]:
    """
    Return a list of open-market insider transactions for *ticker* over the
    last *days* calendar days.  Each dict contains at minimum:

        name             str   insider's name
        transactionCode  str   "P" (purchase) or "S" (sale)
        transactionDate  str   "YYYY-MM-DD"
        share            int   number of shares (may be negative for sales)
        transactionPrice float price per share

    Returns an empty list on any error so callers can treat missing data as
    neutral rather than crashing the pipeline.
    """
    if not FINNHUB_API_KEY:
        log.warning("FINNHUB_API_KEY not set — insider data unavailable")
        return []

    to_date   = date.today()
    from_date = to_date - timedelta(days=days)

    try:
        resp = requests.get(
            f"{_BASE}/stock/insider-transactions",
            params={
                "symbol": ticker,
                "from":   from_date.isoformat(),
                "to":     to_date.isoformat(),
                "token":  FINNHUB_API_KEY,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Insider fetch failed for %s: %s", ticker, exc)
        return []

    raw = resp.json().get("data") or []

    # Keep only signal-bearing codes; drop grants, gifts, etc.
    filtered = [t for t in raw if t.get("transactionCode") in _SIGNAL_CODES]
    log.debug("Insider %s: %d transactions (%d signal-bearing) in last %dd",
              ticker, len(raw), len(filtered), days)
    return filtered
