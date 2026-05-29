"""
Run a backtest of the momentum strategy over the configured date range.

Usage:
    python scripts/run_backtest.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib
matplotlib.use("Agg")   # non-interactive — must be set before importing pyplot
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config.settings import (
    BACKTEST_END,
    BACKTEST_INITIAL_CASH,
    BACKTEST_SLIPPAGE_PCT,
    BACKTEST_START,
    BENCHMARK,
    CASH_BUFFER_PCT,
    MOMENTUM_LOOKBACK_DAYS,
    TOP_N,
    UNIVERSE,
)
from src.backtest.momentum_strategy import run_backtest
from src.data_pipeline.fetch_prices import fetch_one, load_prices, load_universe
from src.utils.logging import get_logger

log = get_logger(__name__)

CHART_PATH = Path(__file__).resolve().parents[1] / "data" / "backtest_chart.png"


def _load_or_fetch(ticker: str, start: str, end: str) -> pd.DataFrame:
    try:
        return load_prices(ticker)
    except FileNotFoundError:
        log.info("%s not cached — fetching now", ticker)
        return fetch_one(ticker, start, end)


def _spy_normalized(spy_df: pd.DataFrame, dates: list, initial_cash: float) -> np.ndarray:
    """Align SPY close prices to strategy dates and normalize to initial_cash."""
    series = spy_df["Close"].copy()
    series.index = pd.to_datetime(series.index)
    aligned = series.reindex(pd.DatetimeIndex(dates), method="ffill")
    return aligned.values / aligned.values[0] * initial_cash


def _build_chart(results: dict, spy_df: pd.DataFrame, initial_cash: float, start: str, end: str):
    dates = results["dates"]
    strat_vals = np.array(results["portfolio_values"])
    spy_vals = _spy_normalized(spy_df, dates, initial_cash)
    date_index = pd.DatetimeIndex(dates)

    # Drawdown of strategy
    peak = np.maximum.accumulate(strat_vals)
    drawdown_pct = (strat_vals - peak) / peak * 100

    fig, (ax1, ax2) = plt.subplots(
        2, 1,
        figsize=(13, 8),
        gridspec_kw={"height_ratios": [3, 1]},
        sharex=True,
    )

    BG_DARK = "#0f0f0f"
    BG_PLOT = "#1a1a1a"
    GRID_COLOR = "#2a2a2a"
    TEXT_COLOR = "#cccccc"

    fig.patch.set_facecolor(BG_DARK)
    for ax in (ax1, ax2):
        ax.set_facecolor(BG_PLOT)
        ax.tick_params(colors=TEXT_COLOR, labelsize=9)
        for spine in ax.spines.values():
            spine.set_edgecolor("#333333")

    # --- Top panel: portfolio value ---
    ax1.plot(date_index, strat_vals, color="#4fc3f7", linewidth=1.6, label="Momentum Strategy", zorder=3)
    ax1.plot(date_index, spy_vals,   color="#ff8a65", linewidth=1.6, label="SPY Buy & Hold",    zorder=2, alpha=0.85)
    ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax1.set_ylabel("Portfolio Value", color=TEXT_COLOR, fontsize=10)
    ax1.set_title(
        f"Momentum Strategy vs SPY Buy & Hold  |  {start} to {end}",
        color="#ffffff", fontsize=12, pad=10,
    )
    ax1.legend(facecolor=BG_PLOT, edgecolor="#444444", labelcolor=TEXT_COLOR, fontsize=9)
    ax1.grid(True, color=GRID_COLOR, linewidth=0.5)

    # --- Bottom panel: drawdown ---
    ax2.fill_between(date_index, drawdown_pct, 0, color="#ef5350", alpha=0.75, label="Strategy Drawdown")
    ax2.set_ylabel("Drawdown (%)", color=TEXT_COLOR, fontsize=10)
    ax2.set_xlabel("Date", color=TEXT_COLOR, fontsize=10)
    ax2.grid(True, color=GRID_COLOR, linewidth=0.5)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=30, ha="right", color=TEXT_COLOR)

    plt.tight_layout(pad=1.5)
    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(CHART_PATH, dpi=150, bbox_inches="tight", facecolor=BG_DARK)
    plt.close(fig)
    log.info("Chart saved: %s", CHART_PATH)


def _print_results(results: dict, spy_df: pd.DataFrame, initial_cash: float, start: str, end: str):
    dates = results["dates"]
    if not dates:
        log.warning("No portfolio data collected — check date range or cache.")
        return

    strat_vals = np.array(results["portfolio_values"])
    spy_vals = _spy_normalized(spy_df, dates, initial_cash)

    final_strat = strat_vals[-1]
    final_spy = spy_vals[-1]

    strat_ret  = (final_strat / initial_cash - 1) * 100
    spy_ret    = (final_spy   / initial_cash - 1) * 100
    alpha      = strat_ret - spy_ret

    years = (dates[-1] - dates[0]).days / 365.25
    strat_cagr = ((final_strat / initial_cash) ** (1 / years) - 1) * 100 if years > 0 else 0.0
    spy_cagr   = ((final_spy   / initial_cash) ** (1 / years) - 1) * 100 if years > 0 else 0.0

    sharpe   = results["sharpe"]
    max_dd   = results["max_drawdown"]
    n_trades = results["total_trades"]

    def fmt_pct(v: float) -> str:
        return f"+{v:.1f}%" if v >= 0 else f"{v:.1f}%"

    W = 54
    bar = "=" * W
    thin = "-" * (W - 2)

    print(f"\n{bar}")
    print(f"  MOMENTUM STRATEGY BACKTEST")
    print(f"  {start} to {end}   |   Starting Capital: ${initial_cash:,.0f}")
    print(bar)
    print(f"  RETURNS")
    print(f"  {'Strategy Total Return':<32} {fmt_pct(strat_ret):>10}")
    print(f"  {'SPY Buy-and-Hold':<32} {fmt_pct(spy_ret):>10}")
    print(f"  {'Alpha vs SPY':<32} {fmt_pct(alpha):>10}")
    print(f"  {'Strategy CAGR':<32} {fmt_pct(strat_cagr):>10}")
    print(f"  {'SPY CAGR':<32} {fmt_pct(spy_cagr):>10}")
    print(f"  {thin}")
    print(f"  RISK")
    sharpe_str = f"{sharpe:.2f}" if sharpe is not None else "N/A"
    print(f"  {'Sharpe Ratio':<32} {sharpe_str:>10}")
    print(f"  {'Max Drawdown':<32} {f'-{max_dd:.1f}%':>10}")
    print(f"  {thin}")
    print(f"  ACTIVITY")
    print(f"  {'Total Trades (closed)':<32} {n_trades:>10}")
    print(bar)
    print(f"  Chart: {CHART_PATH}")
    print(f"{bar}\n")


def main():
    log.info("Loading cached prices for %d tickers...", len(UNIVERSE))
    prices = load_universe(UNIVERSE)
    spy_df = _load_or_fetch(BENCHMARK, BACKTEST_START, BACKTEST_END)

    results = run_backtest(
        prices=prices,
        spy_df=spy_df,
        start=BACKTEST_START,
        end=BACKTEST_END,
        initial_cash=BACKTEST_INITIAL_CASH,
        lookback=MOMENTUM_LOOKBACK_DAYS,
        top_n=TOP_N,
        buffer=0,
        cash_buffer=CASH_BUFFER_PCT,
        commission=BACKTEST_SLIPPAGE_PCT,
    )

    _print_results(results, spy_df, BACKTEST_INITIAL_CASH, BACKTEST_START, BACKTEST_END)

    if results["portfolio_values"]:
        _build_chart(results, spy_df, BACKTEST_INITIAL_CASH, BACKTEST_START, BACKTEST_END)


if __name__ == "__main__":
    main()
