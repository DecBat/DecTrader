# DecTrader

A momentum-based algorithmic trading system for paper trading via Alpaca. Screens the S&P 500 using the Clenow quality-momentum strategy, cross-references SEC insider buying data, applies an LLM sentiment veto gate, and executes equal-weight rebalancing orders automatically each morning.

```
[Price Cache]──>[Momentum Screen]──>[Insider Screen]──>[Sentiment Filter]──>[Alpaca Orders]
   yfinance          Clenow/R²         SEC Form 4          LM Studio            paper API
   ~500 tickers      top 5 picks       top 3 picks         LLM veto             notional $
```

Everything runs against **Alpaca paper trading**. `PAPER_TRADING_ONLY = True` is enforced in code — switching to live requires an explicit config change.

---

## Strategy

**Momentum screener** ranks S&P 500 stocks by Clenow score (annualised OLS slope × R² on log-price). The most recent 21 days are skipped to avoid short-term reversal. Top 5 picks are selected.

**Insider screener** independently scans all ~500 universe tickers for recent open-market purchases by corporate insiders (SEC Form 4 via Finnhub). Scores are recency-weighted dollar values with a 1.5× multiplier for cluster buys (2+ insiders buying within 30 days). Top 3 picks are selected. Runs in parallel with momentum — insider picks can surface stocks before any price trend has developed.

**Sentiment filter** sends each candidate's recent news headlines to a locally-running LM Studio instance (Qwen 2.5 32B or similar). Returns positive/negative/neutral probabilities. Vetoes any pick where P(negative) > 0.60.

**SPY trend filter** goes to cash when SPY closes below its 200-day SMA, regardless of individual stock signals.

**Execution** rebalances to equal-weight across approved picks, keeping a 5% cash buffer. Uses notional dollar orders (fractional share support).

---

## Setup

**Requirements:** Python 3.11+, [LM Studio](https://lmstudio.ai) running locally with a model loaded, Alpaca paper account, Finnhub free account.

```powershell
# 1. Clone and create venv
git clone https://github.com/<your-username>/DecTrader.git
cd DecTrader
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 2. Configure environment
copy .env.example .env   # then fill in your keys
```

**`.env` keys required:**
```
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_BASE_URL=https://paper-api.alpaca.markets
FINNHUB_API_KEY=
LM_STUDIO_URL=http://localhost:1234
```

Get keys at: [alpaca.markets](https://alpaca.markets) · [finnhub.io](https://finnhub.io) · [lmstudio.ai](https://lmstudio.ai)

---

## Usage

```powershell
# Verify Alpaca connection and current positions
.venv\Scripts\python.exe scripts/check_alpaca_connection.py

# Refresh price cache (incremental — skips up-to-date tickers)
.venv\Scripts\python.exe scripts/fetch_data.py

# Run full daily pipeline (requires LM Studio running)
.venv\Scripts\python.exe scripts/run_daily.py

# Run momentum + sentiment screener only (no orders)
.venv\Scripts\python.exe scripts/run_screener.py

# Run backtest (2007–2024 by default)
.venv\Scripts\python.exe scripts/run_backtest.py
```

**Automating with Task Scheduler (Windows):**

Load the LM Studio model at 7:45 AM:
```powershell
$a = New-ScheduledTaskAction -Execute "lms" -Argument "load <model-name>"; $t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "07:45AM"; Register-ScheduledTask -Action $a -Trigger $t -TaskName "DecTrader Load Model"
```

Run the pipeline at 8:00 AM:
```powershell
$a = New-ScheduledTaskAction -Execute "C:\path\to\DecTrader\.venv\Scripts\python.exe" -Argument "scripts/run_daily.py" -WorkingDirectory "C:\path\to\DecTrader"; $t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "08:00AM"; $s = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable; Register-ScheduledTask -Action $a -Trigger $t -Settings $s -TaskName "DecTrader Daily"
```

Enable wake timers so the PC wakes from sleep automatically:
```powershell
powercfg /setacvalueindex SCHEME_CURRENT 238c9fa8-0aad-41ed-83f4-97be242c8f20 bd3b718a-0680-4d9d-8ab2-e1d2b4ac806d 1; powercfg /setactive SCHEME_CURRENT
```

---

## Configuration

All parameters live in `config/settings.py`:

| Parameter | Default | Description |
|---|---|---|
| `TOP_N` | 5 | Momentum picks to hold |
| `TOP_N_INSIDER` | 3 | Insider picks added to pool |
| `MOMENTUM_LOOKBACK_DAYS` | 90 | OLS regression window |
| `INSIDER_LOOKBACK_DAYS` | 60 | Form 4 scan window |
| `CASH_BUFFER_PCT` | 0.05 | Cash reserve (5%) |
| `SENTIMENT_VETO_NEGATIVE` | 0.60 | Veto if P(neg) exceeds this |
| `PAPER_TRADING_ONLY` | True | Safety guard — never change without review |

---

## Repo layout

```
DecTrader/
├── config/settings.py              # all tuneable parameters
├── scripts/
│   ├── run_daily.py                # full pipeline — run each morning
│   ├── run_backtest.py             # historical backtest vs SPY
│   ├── run_screener.py             # screener only, no orders
│   ├── fetch_data.py               # refresh price cache
│   ├── check_alpaca_connection.py  # smoke test
│   └── update_universe.py          # refresh S&P 500 ticker list
├── src/
│   ├── data_pipeline/
│   │   ├── fetch_prices.py         # yfinance → parquet cache
│   │   └── fetch_insider.py        # Finnhub Form 4 fetcher
│   ├── screeners/
│   │   ├── base.py                 # ScreenerPick, BaseScreener ABC
│   │   ├── momentum.py             # Clenow momentum screener
│   │   └── insider.py              # SEC Form 4 insider screener
│   ├── sentiment/
│   │   ├── news_fetcher.py         # Finnhub news API
│   │   ├── finbert_scorer.py       # LM Studio scorer (OpenAI-compatible)
│   │   ├── filter.py               # SentimentFilter veto gate
│   │   └── insider_scorer.py       # InsiderSignal scoring utilities
│   ├── backtest/
│   │   └── momentum_strategy.py    # backtrader strategy + run_backtest()
│   ├── execution/
│   │   └── alpaca_trader.py        # AlpacaTrader: rebalance, go_to_cash
│   └── utils/logging.py
├── data/                           # gitignored — parquet price cache
├── logs/                           # gitignored — daily log files
├── requirements.txt
└── .env                            # gitignored — API keys
```

---

## Backtest results (2007–2024)

> **Survivorship bias warning:** the universe is the current S&P 500 constituent list, which contains only companies that survived to today. These results are an upper bound on real forward returns.

| Metric | Strategy | SPY buy-and-hold |
|---|---|---|
| Total return | +5,016% | +631% |
| Sharpe ratio | 0.99 | — |
| Max drawdown | -26.4% | — |
| Trades (closed) | 699 | — |

---

## Reminders

- Paper trading does not simulate slippage, real liquidity, or dividends
- Backtests suffer from survivorship bias — real forward returns will be lower
- Insider scan takes ~8–9 minutes (Finnhub rate limit); total daily runtime ~20 minutes
- LM Studio must be running before the pipeline starts; the system falls back to neutral sentiment if it is unreachable
- If paper P&L cannot beat holding SPY after 3 months, the strategy needs rethinking before committing real money

---

## AI Disclosure

This project was built with the assistance of [Claude](https://claude.ai) (Anthropic). AI was used in development for architecture design, code generation, debugging, and documentation. All code has been reviewed, tested, and is operated by a human. Trading decisions are made autonomously by the system based on rules defined by the developer — no AI is involved at runtime.

---

## References

- [Teddy Koker — Momentum strategy](https://teddykoker.com/2019/05/momentum-strategy-from-stocks-on-the-move-in-python/)
- [Andreas Clenow — Stocks on the Move](https://www.followingthetrend.com/stocks-on-the-move/)
- [Alpaca paper trading](https://alpaca.markets/learn/start-paper-trading)
- [Backtrader docs](https://www.backtrader.com/docu/)
- [Finnhub API](https://finnhub.io/docs/api)
