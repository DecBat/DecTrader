"""
Run a backtest of the momentum strategy over the configured date range.

Should:
  - Load cached prices for the universe
  - Set up Cerebro with MomentumStrategy
  - Add analyzers: SharpeRatio, DrawDown, TradeAnalyzer
  - Compare final return to SPY buy-and-hold over the same period
  - Optionally plot results

Usage:
    python scripts/run_backtest.py
"""
