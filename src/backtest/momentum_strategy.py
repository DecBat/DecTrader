"""
Backtrader momentum strategy — Clenow / Teddy Koker quality-momentum.
"""
from __future__ import annotations

from datetime import date as Date

import backtrader as bt
import numpy as np
import pandas as pd

from src.utils.logging import get_logger

log = get_logger(__name__)

SKIP_DAYS = 21  # drop most-recent ~1 month to avoid short-term reversal


def _clenow_score(series: np.ndarray) -> float:
    """Annualized slope * R² on log-price regression. Returns nan if degenerate."""
    if len(series) < 10 or np.any(series <= 0):
        return float("nan")
    x = np.arange(len(series))
    y = np.log(series.astype(float))
    slope, intercept = np.polyfit(x, y, 1)
    y_hat = slope * x + intercept
    ss_res = np.sum((y - y_hat) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return ((np.exp(slope) ** 252) - 1) * r2


class MomentumStrategy(bt.Strategy):
    params = dict(
        lookback=90,
        top_n=5,
        buffer=3,               # hold existing positions until they fall outside top N+buffer
        rebalance_interval=5,   # bars between rebalances (5 ≈ weekly)
        trend_filter=True,
        sma_period=200,
        cash_buffer=0.05,
    )

    def __init__(self):
        # datas[0] is SPY — used only as trend-filter benchmark, never traded
        self.spy = self.datas[0]
        self.spy_sma = bt.indicators.SMA(self.spy.close, period=self.p.sma_period)
        self.name_to_data = {d._name: d for d in self.datas}

        # Collected every bar for post-run charting
        self.portfolio_values: list[float] = []
        self.dates: list[Date] = []
        self._bar = 0

    def next(self):
        self.portfolio_values.append(self.broker.getvalue())
        self.dates.append(self.data.datetime.date(0))

        self._bar += 1
        if self._bar % self.p.rebalance_interval != 0:
            return

        # Trend filter: go to cash when SPY is below its 200-day SMA
        if self.p.trend_filter and self.spy.close[0] < self.spy_sma[0]:
            for d in self.datas[1:]:
                if self.getposition(d).size:
                    self.order_target_percent(d, 0.0)
            log.debug("%s: SPY below 200d SMA — holding cash", self.data.datetime.date(0))
            return

        # Score every non-SPY feed
        needed = self.p.lookback + SKIP_DAYS
        scores: dict[str, float] = {}
        for d in self.datas[1:]:
            if len(d) < needed:
                continue
            # close.get() returns values chronologically (oldest first, newest last)
            vals = np.array(d.close.get(size=needed))
            series = vals[:-SKIP_DAYS]   # drop most-recent SKIP_DAYS
            score = _clenow_score(series)
            if not np.isnan(score) and score > 0:
                scores[d._name] = score

        ranked = sorted(scores, key=scores.__getitem__, reverse=True)

        # buy_zone  — top N: actively buy if not held
        # hold_zone — top N+buffer: keep if already held, don't buy if not
        # outside   — sell immediately
        buy_zone  = set(ranked[: self.p.top_n])
        hold_zone = set(ranked[: self.p.top_n + self.p.buffer])

        # Sell anything that has fallen outside the hold zone
        for d in self.datas[1:]:
            if d._name not in hold_zone and self.getposition(d).size:
                self.order_target_percent(d, 0.0)

        if not buy_zone:
            return

        # Active set = buy zone + any currently held positions still inside hold zone
        held_in_buffer = {
            d._name for d in self.datas[1:]
            if d._name in hold_zone and self.getposition(d).size
        }
        active = buy_zone | held_in_buffer

        # Equal-weight across the full active set
        target_pct = (1.0 - self.p.cash_buffer) / len(active)
        for ticker in active:
            self.order_target_percent(self.name_to_data[ticker], target_pct)

        log.debug("%s | buy=%s buffer_held=%s",
                  self.data.datetime.date(0),
                  sorted(buy_zone),
                  sorted(held_in_buffer - buy_zone))


def _make_feed(df: pd.DataFrame, name: str, fromdate: str, todate: str) -> bt.feeds.PandasData:
    """Convert a parquet DataFrame into a backtrader data feed."""
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]   # backtrader expects lowercase
    df.index = pd.to_datetime(df.index)
    df = df.loc[fromdate:todate]
    return bt.feeds.PandasData(
        dataname=df,
        name=name,
        datetime=None,
        open="open",
        high="high",
        low="low",
        close="close",
        volume="volume",
        openinterest=-1,
    )


def run_backtest(
    prices: dict[str, pd.DataFrame],
    spy_df: pd.DataFrame,
    start: str,
    end: str,
    initial_cash: float = 100_000.0,
    lookback: int = 90,
    top_n: int = 5,
    buffer: int = 3,
    cash_buffer: float = 0.05,
    commission: float = 0.001,
) -> dict:
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=commission)

    # SPY must be datas[0] — it is the trend-filter reference, not traded
    cerebro.adddata(_make_feed(spy_df, "SPY", start, end))
    for ticker, df in prices.items():
        cerebro.adddata(_make_feed(df, ticker, start, end))

    cerebro.addstrategy(
        MomentumStrategy,
        lookback=lookback,
        top_n=top_n,
        buffer=buffer,
        cash_buffer=cash_buffer,
    )

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe",
                        timeframe=bt.TimeFrame.Days, annualize=True, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    log.info("Running backtest %s → %s  |  initial cash $%.0f", start, end, initial_cash)
    results = cerebro.run()
    strat = results[0]

    sharpe_val = strat.analyzers.sharpe.get_analysis().get("sharperatio")
    max_dd = strat.analyzers.drawdown.get_analysis().get("max", {}).get("drawdown", 0.0)
    total_trades = strat.analyzers.trades.get_analysis().get("total", {}).get("closed", 0)

    return {
        "portfolio_values": strat.portfolio_values,
        "dates": strat.dates,
        "final_value": strat.portfolio_values[-1] if strat.portfolio_values else initial_cash,
        "sharpe": sharpe_val,
        "max_drawdown": max_dd,
        "total_trades": total_trades,
    }
