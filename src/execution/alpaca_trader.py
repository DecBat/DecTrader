"""
Alpaca paper trading execution layer.
"""
from __future__ import annotations

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from config.settings import (
    ALPACA_API_KEY,
    ALPACA_SECRET_KEY,
    ALPACA_BASE_URL,
    CASH_BUFFER_PCT,
    MAX_DAILY_TRADES,
    PAPER_TRADING_ONLY,
)
from src.utils.logging import get_logger

log = get_logger(__name__)

_LIVE_URL = "https://api.alpaca.markets"


class AlpacaTrader:
    def __init__(self):
        if PAPER_TRADING_ONLY and ALPACA_BASE_URL.rstrip("/") == _LIVE_URL:
            raise RuntimeError(
                "PAPER_TRADING_ONLY is True but ALPACA_BASE_URL points to the live "
                "endpoint. Set ALPACA_BASE_URL=https://paper-api.alpaca.markets in .env."
            )
        self._client = TradingClient(
            api_key=ALPACA_API_KEY,
            secret_key=ALPACA_SECRET_KEY,
            paper=True,
        )
        self._orders_today = 0
        log.info("AlpacaTrader ready  paper=True  circuit_breaker=%d", MAX_DAILY_TRADES)

    # ------------------------------------------------------------------
    # Read-only helpers
    # ------------------------------------------------------------------

    def account_summary(self) -> dict:
        """Return key account metrics."""
        a = self._client.get_account()
        return {
            "equity": float(a.equity),
            "cash": float(a.cash),
            "buying_power": float(a.buying_power),
        }

    def get_positions(self) -> dict[str, float]:
        """Return {symbol: market_value} for all open positions."""
        return {p.symbol: float(p.market_value) for p in self._client.get_all_positions()}

    # ------------------------------------------------------------------
    # Rebalancing
    # ------------------------------------------------------------------

    def rebalance(self, target_tickers: list[str]) -> None:
        """
        Rebalance portfolio to equal-weight target_tickers with CASH_BUFFER_PCT reserve.

        - Closes any position not in target_tickers.
        - Buys into or trims each target position toward equal weight.
        - Stops submitting orders once MAX_DAILY_TRADES is reached.

        Call this after market open with the screener's output.
        """
        if not target_tickers:
            log.warning("rebalance() called with empty target — no action taken")
            return

        account = self._client.get_account()
        equity = float(account.equity)
        target_each = equity * (1.0 - CASH_BUFFER_PCT) / len(target_tickers)

        log.info(
            "Rebalancing -> %d positions | equity=$%.2f | target each=$%.2f",
            len(target_tickers), equity, target_each,
        )

        # Snapshot current positions before any orders
        positions = {p.symbol: p for p in self._client.get_all_positions()}
        target_set = set(target_tickers)

        # Step 1: Close exits first so capital is free for step 2
        for symbol, pos in positions.items():
            if symbol not in target_set:
                self._close_position(symbol, float(pos.market_value))

        # Step 2: Buy new entries / adjust existing positions
        for symbol in target_tickers:
            current_val = float(positions[symbol].market_value) if symbol in positions else 0.0
            diff = target_each - current_val

            if diff > 1.0:
                self._submit_notional(symbol, OrderSide.BUY, diff)
            elif diff < -1.0:
                # Trim overweight, capped at the actual position size
                self._submit_notional(symbol, OrderSide.SELL, min(abs(diff), current_val))

    def go_to_cash(self) -> None:
        """Close every open position. Used when SPY trend filter triggers or all picks are vetoed."""
        positions = {p.symbol: p for p in self._client.get_all_positions()}
        if not positions:
            log.info("Already in cash — nothing to close")
            return
        log.info("Going to cash — closing %d positions", len(positions))
        for symbol, pos in positions.items():
            self._close_position(symbol, float(pos.market_value))

    def cancel_all_orders(self) -> None:
        """Cancel all pending open orders. Use before a rebalance if needed."""
        self._client.cancel_orders()
        log.info("All open orders cancelled")

    # ------------------------------------------------------------------
    # Internal order helpers
    # ------------------------------------------------------------------

    def _close_position(self, symbol: str, market_value: float) -> None:
        if not self._within_circuit_breaker(symbol):
            return
        try:
            self._client.close_position(symbol)
            self._orders_today += 1
            log.info("EXIT  %-6s  market_value=$%.2f", symbol, market_value)
        except Exception as exc:
            log.error("Failed to close %s: %s", symbol, exc)

    def _submit_notional(self, symbol: str, side: OrderSide, notional: float) -> None:
        if not self._within_circuit_breaker(symbol):
            return
        try:
            order = self._client.submit_order(
                MarketOrderRequest(
                    symbol=symbol,
                    notional=round(notional, 2),
                    side=side,
                    time_in_force=TimeInForce.DAY,
                )
            )
            self._orders_today += 1
            log.info(
                "%-4s  %-6s  notional=$%.2f  id=%s",
                side.value.upper(), symbol, notional, order.id,
            )
        except Exception as exc:
            log.error("Order failed %s %s $%.2f: %s", side.value, symbol, notional, exc)

    def _within_circuit_breaker(self, symbol: str) -> bool:
        if self._orders_today >= MAX_DAILY_TRADES:
            log.warning(
                "MAX_DAILY_TRADES=%d reached — skipping %s",
                MAX_DAILY_TRADES, symbol,
            )
            return False
        return True
