"""
Full daily pipeline: data refresh -> screener -> sentiment filter -> paper orders.

Pseudocode:
    1. update_cache() to refresh prices
    2. picks = MomentumScreener().screen(load_universe())
    3. filter = SentimentFilter()
    4. for each pick:
         if filter.allow_trade(pick.ticker):
             trader.submit_market_order(...)
    5. log everything

Schedule this with cron, Task Scheduler, or just run manually each morning
before market open. Keep MAX_DAILY_TRADES low while you're learning.

Usage:
    python scripts/run_daily.py
"""
