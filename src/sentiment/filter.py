"""
Sentiment trade gate — combines news fetcher + LM Studio scorer into a one-way veto.

Design: sentiment can BLOCK a trade but never INITIATE one.
If a ticker has no recent news, the trade is allowed (benefit of the doubt).
"""
from __future__ import annotations

from config.settings import SENTIMENT_VETO_NEGATIVE
from src.sentiment.finbert_scorer import SentimentScore, score_texts
from src.sentiment.news_fetcher import fetch_news
from src.utils.logging import get_logger

log = get_logger(__name__)


class SentimentFilter:
    def __init__(
        self,
        lookback_days: int = 7,
        veto_threshold: float = SENTIMENT_VETO_NEGATIVE,
    ):
        self.lookback_days = lookback_days
        self.veto_threshold = veto_threshold

    def score(self, ticker: str) -> SentimentScore:
        """Fetch news and return averaged FinBERT scores for ticker."""
        articles = fetch_news(ticker, self.lookback_days)
        if not articles:
            return SentimentScore(positive=0.0, negative=0.0, neutral=1.0, n_items=0)

        texts = [
            f"{a['headline']}. {a['summary']}".strip(". ").strip()
            for a in articles
        ]
        texts = [t for t in texts if t]
        return score_texts(texts)

    def allow_trade(self, ticker: str) -> tuple[bool, SentimentScore]:
        """
        Returns (allowed, sentiment).
        allowed=False means sentiment is strongly negative — veto the trade.
        allowed=True  when no news exists or negativity is below threshold.
        """
        sentiment = self.score(ticker)

        if sentiment.n_items == 0:
            log.info("%s: no recent news — trade allowed by default", ticker)
            return True, sentiment

        if sentiment.negative > self.veto_threshold:
            log.info(
                "%s: VETOED  P(neg)=%.2f > threshold %.2f | %s",
                ticker, sentiment.negative, self.veto_threshold, sentiment.reasoning,
            )
            return False, sentiment

        log.info(
            "%s: allowed  P(neg)=%.2f  P(pos)=%.2f  n=%d | %s",
            ticker, sentiment.negative, sentiment.positive,
            sentiment.n_items, sentiment.reasoning,
        )
        return True, sentiment
