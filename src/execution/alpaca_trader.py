"""
Alpaca paper trading client.

Build an AlpacaTrader class that:
  - Refuses to instantiate if PAPER_TRADING_ONLY is True but base URL is live
  - Wraps alpaca-py's TradingClient
  - Exposes: account_summary(), positions(), submit_market_order(), size_position()
  - Enforces MAX_DAILY_TRADES as a circuit breaker

Use alpaca-py (the current SDK), not the deprecated alpaca-trade-api.

Key SDK imports:
  from alpaca.trading.client import TradingClient
  from alpaca.trading.requests import MarketOrderRequest
  from alpaca.trading.enums import OrderSide, TimeInForce

Always pass paper=True when constructing TradingClient.
"""
