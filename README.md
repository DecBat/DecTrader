# AI Trading Starter

Paper-trading skeleton that wires together four layers:

```
[Data Pipeline] -> [Screener] -> [Sentiment Filter] -> [Paper Execution]
   yfinance         pandas         FinBERT/news          Alpaca paper API
```

Everything runs against **Alpaca paper trading**. No real money.

## Setup

1. Install Python 3.11+
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate     # macOS/Linux
   # .venv\Scripts\activate      # Windows
   pip install -r requirements.txt
   ```
3. Get Alpaca paper API keys at https://alpaca.markets
4. Copy `.env.example` to `.env` and fill in your keys

## Repo layout

```
ai-trading-starter/
├── config/
│   └── settings.py             # central config: universe, thresholds, paper-mode flag
├── data/                       # local price cache (gitignored)
├── logs/                       # trade and run logs (gitignored)
├── notebooks/                  # Jupyter notebooks for exploration
├── scripts/                    # entry-point scripts you run from the command line
│   ├── check_alpaca_connection.py
│   ├── fetch_data.py
│   ├── run_screener.py
│   ├── run_backtest.py
│   └── run_daily.py            # full pipeline: data -> screen -> sentiment -> orders
├── src/
│   ├── data_pipeline/          # yfinance fetching, parquet caching
│   ├── screeners/              # momentum, mean reversion, etc.
│   ├── sentiment/              # news fetcher + FinBERT scorer + filter
│   ├── execution/              # Alpaca client wrapper with paper-mode guard
│   ├── backtest/               # backtrader strategy classes
│   └── utils/                  # logging, helpers
├── tests/                      # pytest tests
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Suggested build order

Build one piece at a time. Each step should work end-to-end before you move on.

1. **Verify Alpaca connection** — fill in `scripts/check_alpaca_connection.py`
2. **Build the data pipeline** — `src/data_pipeline/fetch_prices.py` + `scripts/fetch_data.py`
3. **Write one screener** — `src/screeners/momentum.py` + `scripts/run_screener.py`
4. **Backtest it** — `src/backtest/momentum_strategy.py` + `scripts/run_backtest.py`
5. **Add sentiment filter** — `src/sentiment/news_fetcher.py` + `finbert_scorer.py` + `filter.py`
6. **Wire up paper execution** — `src/execution/alpaca_trader.py`
7. **Tie it together** — `scripts/run_daily.py`

## What's NOT here (intentionally)

- **No live trading.** Paper mode should be enforced via a flag in `config/settings.py`. Flipping to live should require deliberate code changes.
- **No magic AI.** FinBERT is a sentiment classifier used as a *filter* on top of a quantitative signal, not as a primary signal.

## Reminders

- Paper trading does not simulate slippage, real liquidity, or dividends.
- Backtests suffer from look-ahead bias, survivorship bias, and overfitting unless you actively control for them.
- If your paper P&L can't beat just holding SPY, the strategy is not worth running with real money.

## References

- Alpaca paper trading: https://alpaca.markets/learn/start-paper-trading
- Backtrader quickstart: https://www.backtrader.com/docu/quickstart/quickstart/
- Teddy Koker momentum strategy: https://teddykoker.com/2019/05/momentum-strategy-from-stocks-on-the-move-in-python/
- FinBERT: https://huggingface.co/ProsusAI/finbert
