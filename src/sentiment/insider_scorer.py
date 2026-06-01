"""
Insider trading signal scorer.

Reads SEC Form 4 open-market transactions (via Finnhub) and classifies
each ticker as BULLISH, NEUTRAL, or BEARISH based on recent insider activity.

Signal logic
------------
BULLISH  — significant open-market purchasing, or a cluster buy (2+ different
           insiders buying within a 30-day window).  Research consistently
           shows cluster buys are the highest-conviction insider signal.

BEARISH  — heavy net selling (> $500k) with zero open-market purchases in the
           window.  Pure absence of buying + large sales.  Note: isolated sales
           are ignored because insiders sell for many non-predictive reasons
           (taxes, diversification, pre-planned 10b5-1 schedules).

NEUTRAL  — everything else: small purchases below the significance threshold,
           mixed activity, or no transactions at all.

Used as a veto gate in run_daily.py: BEARISH blocks the trade; BULLISH and
NEUTRAL pass through to the sentiment filter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from src.data_pipeline.fetch_insider import fetch_insider_transactions
from src.utils.logging import get_logger

log = get_logger(__name__)

# --- Thresholds (tune after observing real data) ---
_BULLISH_BUY_USD  = 100_000   # min open-market purchase value to call BULLISH
_BEARISH_SELL_USD = 500_000   # min net-sell value (with zero buys) to call BEARISH
_CLUSTER_DAYS     = 30        # rolling window for cluster-buy detection
_CLUSTER_MIN      = 2         # unique insiders needed for a cluster


@dataclass
class InsiderSignal:
    ticker:      str
    n_buyers:    int             # unique insiders who made open-market purchases
    buy_value:   float           # total $ value of open-market purchases
    sell_value:  float           # total $ value of open-market sales
    cluster_buy: bool            # True if 2+ insiders bought within _CLUSTER_DAYS
    signal:      str             # "BULLISH" | "NEUTRAL" | "BEARISH"
    reasoning:   str = field(default="")

    def __str__(self) -> str:
        return (
            f"{self.signal:<8}  buy=${self.buy_value:>10,.0f}  "
            f"sell=${self.sell_value:>10,.0f}  buyers={self.n_buyers}"
            f"{'  CLUSTER' if self.cluster_buy else ''}"
        )


def _dollar_value(txn: dict) -> float:
    """Return absolute dollar value of a transaction."""
    shares = abs(txn.get("share", 0) or 0)
    price  = abs(txn.get("transactionPrice", 0) or 0)
    return shares * price


def _detect_cluster(buys: list[dict]) -> bool:
    """Return True if 2+ unique insiders bought within any _CLUSTER_DAYS window."""
    if len(buys) < _CLUSTER_MIN:
        return False

    entries: list[tuple[date, str]] = []
    for t in buys:
        try:
            d    = date.fromisoformat(t["transactionDate"])
            name = t.get("name", "unknown")
            entries.append((d, name))
        except (KeyError, ValueError):
            continue

    entries.sort()
    window = timedelta(days=_CLUSTER_DAYS)

    for i, (d_start, _) in enumerate(entries):
        buyers_in_window = {
            name for d, name in entries[i:]
            if d <= d_start + window
        }
        if len(buyers_in_window) >= _CLUSTER_MIN:
            return True
    return False


def score_insider(ticker: str, days: int = 90) -> InsiderSignal:
    """
    Score insider trading activity for *ticker* over the last *days* days.
    Falls back to NEUTRAL on any data error so the pipeline keeps running.
    """
    try:
        transactions = fetch_insider_transactions(ticker, days)
    except Exception as exc:
        log.warning("Insider scoring failed for %s: %s — defaulting neutral", ticker, exc)
        return InsiderSignal(ticker, 0, 0.0, 0.0, False, "NEUTRAL",
                             f"fetch error: {exc}")

    if not transactions:
        return InsiderSignal(ticker, 0, 0.0, 0.0, False, "NEUTRAL",
                             "no open-market transactions in window")

    buys  = [t for t in transactions if t.get("transactionCode") == "P"]
    sells = [t for t in transactions if t.get("transactionCode") == "S"]

    buy_value  = sum(_dollar_value(t) for t in buys)
    sell_value = sum(_dollar_value(t) for t in sells)
    n_buyers   = len({t.get("name", "") for t in buys})
    cluster    = _detect_cluster(buys)

    # --- Classify ---
    if buy_value >= _BULLISH_BUY_USD or cluster:
        signal = "BULLISH"
        if cluster:
            reasoning = (f"cluster buy: {n_buyers} insiders purchased "
                         f"${buy_value:,.0f} total in {days}d window")
        else:
            reasoning = (f"significant purchase: ${buy_value:,.0f} "
                         f"by {n_buyers} insider(s)")

    elif sell_value >= _BEARISH_SELL_USD and buy_value == 0:
        signal = "BEARISH"
        reasoning = (f"heavy selling ${sell_value:,.0f} with no open-market "
                     f"purchases in {days}d window")

    else:
        signal = "NEUTRAL"
        parts = []
        if buy_value > 0:
            parts.append(f"${buy_value:,.0f} bought")
        if sell_value > 0:
            parts.append(f"${sell_value:,.0f} sold")
        reasoning = ", ".join(parts) if parts else "no significant activity"

    log.info("Insider %-6s  %s | %s", ticker, signal, reasoning)

    return InsiderSignal(
        ticker=ticker,
        n_buyers=n_buyers,
        buy_value=round(buy_value, 2),
        sell_value=round(sell_value, 2),
        cluster_buy=cluster,
        signal=signal,
        reasoning=reasoning,
    )


class InsiderFilter:
    """
    Thin wrapper around score_insider() matching the interface of SentimentFilter.
    Returns (allowed: bool, signal: InsiderSignal).
    BEARISH vetoes the trade; BULLISH and NEUTRAL pass through.
    """

    def __init__(self, days: int = 90):
        self._days = days

    def allow_trade(self, ticker: str) -> tuple[bool, InsiderSignal]:
        signal  = score_insider(ticker, self._days)
        allowed = signal.signal != "BEARISH"
        if not allowed:
            log.warning("INSIDER VETO %-6s: %s", ticker, signal.reasoning)
        return allowed, signal
