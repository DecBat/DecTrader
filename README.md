# AI Trading Starter

Paper-trading skeleton that wires together four layers:

```
[Data Pipeline] -> [Screener] -> [Sentiment Filter] -> [Paper Execution]
   yfinance         pandas         FinBERT/news          Alpaca paper API
```

Everything runs against **Alpaca paper trading**.

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

## Reminders

- Paper trading does not simulate slippage, real liquidity, or dividends.
- Backtests suffer from look-ahead bias, survivorship bias, and overfitting unless you actively control for them.
- If your paper P&L can't beat just holding SPY, the strategy is not worth running with real money.

## References

- Alpaca paper trading: https://alpaca.markets/learn/start-paper-trading
- Backtrader quickstart: https://www.backtrader.com/docu/quickstart/quickstart/
- Teddy Koker momentum strategy: https://teddykoker.com/2019/05/momentum-strategy-from-stocks-on-the-move-in-python/
- FinBERT: https://huggingface.co/ProsusAI/finbert
