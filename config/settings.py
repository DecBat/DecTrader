"""
Central configuration.

Put here:
  - Paths (data dir, logs dir)
  - PAPER_TRADING_ONLY flag (safety guard, default True)
  - Alpaca API keys loaded from .env
  - News API keys loaded from .env
  - Trading universe (start with ~20 liquid large-caps)
  - Benchmark ticker (SPY)
  - Strategy parameters (momentum lookback, top N, rebalance frequency)
  - Position sizing rules (max % per position, cash buffer)
  - Risk controls (stop-loss %, max daily trades)
  - Sentiment thresholds (e.g. veto if P(negative) > 0.60)
  - Backtest defaults (start/end dates, initial cash, slippage assumption)
"""
