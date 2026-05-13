"""
FinBERT sentiment scoring.

Model: ProsusAI/finbert (downloads ~440MB on first use, then cached)
Outputs softmax probabilities for [positive, negative, neutral].

Build:
  - Lazy-loaded model + tokenizer (load once per process)
  - SentimentScore dataclass: positive, negative, neutral, n_items
  - score_texts(texts) -> SentimentScore that averages probs across the batch

Aggregating across multiple headlines via average probability gives a more
stable signal than majority vote on noisy individual headlines.

Alternative model worth A/B testing:
  yiyanghkust/finbert-tone (fine-tuned on analyst reports)
"""
