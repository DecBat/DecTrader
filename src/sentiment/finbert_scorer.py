"""
FinBERT sentiment scoring.

Model: ProsusAI/finbert — downloads ~440 MB on first use, then cached locally.
Outputs averaged softmax probabilities across a batch of texts.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from src.utils.logging import get_logger

log = get_logger(__name__)

_MODEL_NAME = "ProsusAI/finbert"
_BATCH_SIZE = 16


@dataclass
class SentimentScore:
    positive: float
    negative: float
    neutral:  float
    n_items:  int

    def __str__(self) -> str:
        return (
            f"pos={self.positive:.2f} neg={self.negative:.2f} "
            f"neu={self.neutral:.2f} n={self.n_items}"
        )


@lru_cache(maxsize=1)
def _load_model() -> tuple:
    """Load tokenizer and model once per process, then cache."""
    log.info("Loading FinBERT model (%s) — first run downloads ~440 MB", _MODEL_NAME)
    tokenizer = AutoTokenizer.from_pretrained(_MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(_MODEL_NAME)
    model.eval()
    return tokenizer, model


def score_texts(texts: list[str]) -> SentimentScore:
    """
    Score a list of financial text strings with FinBERT.
    Returns averaged probabilities across all inputs.
    No news → neutral score with n_items=0.
    """
    if not texts:
        return SentimentScore(positive=0.0, negative=0.0, neutral=1.0, n_items=0)

    tokenizer, model = _load_model()

    # Map label indices using the model's own config to avoid hard-coding order
    id2label = {k: v.lower() for k, v in model.config.id2label.items()}
    label2idx = {v: k for k, v in id2label.items()}

    all_probs: list[torch.Tensor] = []

    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        inputs = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        with torch.no_grad():
            logits = model(**inputs).logits
        all_probs.append(torch.nn.functional.softmax(logits, dim=-1))

    avg = torch.cat(all_probs, dim=0).mean(dim=0)

    return SentimentScore(
        positive=avg[label2idx["positive"]].item(),
        negative=avg[label2idx["negative"]].item(),
        neutral =avg[label2idx["neutral" ]].item(),
        n_items =len(texts),
    )
