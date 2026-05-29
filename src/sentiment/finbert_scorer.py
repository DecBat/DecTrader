"""
LM Studio sentiment scorer.

Replaces the local FinBERT model with a call to a locally-running LM Studio
instance. The API is OpenAI-compatible so the request format is standard.

Configure the target machine in .env:
    LM_STUDIO_URL=http://localhost:1234          # same machine
    LM_STUDIO_URL=http://192.168.1.x:1234        # another machine on LAN

The SentimentScore dataclass and score_texts() signature are unchanged
so filter.py requires no modifications.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import requests

from config.settings import LM_STUDIO_URL
from src.utils.logging import get_logger

log = get_logger(__name__)

_TIMEOUT       = 300  # seconds — 32B model on RAM can take 2-3 min TTFT; 5 min is safe
_MAX_HEADLINES = 10   # cap articles per request; top 10 carry nearly all the signal
_MAX_CHARS     = 300  # truncate each headline+summary — headline alone is ~80 chars
_MAX_TOKENS    = 300  # JSON is ~30 tokens; 300 leaves ~270 tokens for reasoning

_SYSTEM_PROMPT = """You are a financial sentiment analyst. Your job is to analyze \
news headlines and summaries about publicly traded companies and assess the likely \
impact on the stock price over the next 1-4 weeks.

When given a list of headlines, respond only with a JSON object in this exact format:
{
  "positive": 0.0,
  "negative": 0.0,
  "neutral": 0.0,
  "reasoning": "brief explanation"
}

Where positive, negative, and neutral are probabilities that sum to exactly 1.0.

Rules:
- Focus on price impact, not just tone. A CEO resignation may use neutral language \
but is negative for the stock.
- Regulatory investigations, lawsuits, and patent losses are negative.
- Earnings beats, new contracts, share buybacks, and dividend increases are positive.
- Macroeconomic news (Fed rates, inflation) should be assessed for sector-specific impact.
- If headlines are mixed or unrelated to price impact, lean neutral.
- Never refuse to score. Always return valid JSON and nothing else."""


@dataclass
class SentimentScore:
    positive:  float
    negative:  float
    neutral:   float
    n_items:   int
    reasoning: str = field(default="")

    def __str__(self) -> str:
        return (
            f"pos={self.positive:.2f} neg={self.negative:.2f} "
            f"neu={self.neutral:.2f} n={self.n_items}"
        )


def _parse_json(content: str) -> dict:
    """
    Extract and parse JSON from the model response.
    Handles markdown code fences (```json ... ```) and stray surrounding text.
    """
    # Strip markdown code fences if present
    content = re.sub(r"```(?:json)?\s*", "", content).strip().rstrip("`").strip()

    # If there's still non-JSON text before the object, find the first {
    start = content.find("{")
    end   = content.rfind("}") + 1
    if start != -1 and end > start:
        content = content[start:end]

    return json.loads(content)


def _normalize(data: dict) -> tuple[float, float, float]:
    """Ensure probabilities sum to 1.0."""
    pos = float(data.get("positive", 0.0))
    neg = float(data.get("negative", 0.0))
    neu = float(data.get("neutral",  0.0))
    total = pos + neg + neu
    if total <= 0:
        return 0.0, 0.0, 1.0
    return pos / total, neg / total, neu / total


def score_texts(texts: list[str]) -> SentimentScore:
    """
    Send all headlines to LM Studio in a single request and return a SentimentScore.
    Falls back to neutral if LM Studio is unreachable or returns invalid output.
    """
    if not texts:
        return SentimentScore(positive=0.0, negative=0.0, neutral=1.0, n_items=0)

    # Clip to most recent N articles and truncate each to stay within context window.
    # 15 × 300 chars ~ 1 100 tokens + system prompt ~ well within 4 096.
    clipped = [t[:_MAX_CHARS] for t in texts[:_MAX_HEADLINES]]
    if len(texts) > _MAX_HEADLINES:
        log.debug("Trimmed %d articles to %d for context window", len(texts), _MAX_HEADLINES)

    headline_block = "\n".join(f"- {t}" for t in clipped)
    user_message   = f"Analyze the sentiment of these {len(clipped)} financial headlines:\n\n{headline_block}"

    try:
        resp = requests.post(
            f"{LM_STUDIO_URL}/v1/chat/completions",
            json={
                "model":       "local-model",
                "messages":    [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
                "temperature": 0.1,
                "max_tokens":  _MAX_TOKENS,
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()

    except requests.ConnectionError:
        log.warning("LM Studio unreachable at %s — defaulting to neutral", LM_STUDIO_URL)
        return SentimentScore(positive=0.0, negative=0.0, neutral=1.0, n_items=len(texts),
                              reasoning="LM Studio unreachable")
    except requests.Timeout:
        log.warning("LM Studio timed out after %ds — defaulting to neutral", _TIMEOUT)
        return SentimentScore(positive=0.0, negative=0.0, neutral=1.0, n_items=len(texts),
                              reasoning="LM Studio timed out")
    except requests.RequestException as exc:
        log.warning("LM Studio request failed: %s — defaulting to neutral", exc)
        return SentimentScore(positive=0.0, negative=0.0, neutral=1.0, n_items=len(texts),
                              reasoning=str(exc))

    content = resp.json()["choices"][0]["message"]["content"]
    log.debug("LM Studio raw response: %s", content)

    try:
        data = _parse_json(content)
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("Could not parse LM Studio response as JSON: %s", exc)
        return SentimentScore(positive=0.0, negative=0.0, neutral=1.0, n_items=len(texts),
                              reasoning="JSON parse error")

    pos, neg, neu = _normalize(data)
    reasoning     = data.get("reasoning", "")

    log.info("Scored %d headlines: pos=%.2f neg=%.2f neu=%.2f | %s",
             len(texts), pos, neg, neu, reasoning)

    return SentimentScore(
        positive=round(pos, 3),
        negative=round(neg, 3),
        neutral =round(neu, 3),
        n_items =len(texts),   # original fetch count, not the clipped count
        reasoning=reasoning,
    )
