"""
Central configuration.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Paths ---
ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
LOGS_DIR = ROOT_DIR / "logs"
PRICES_DIR = DATA_DIR / "prices"

# --- Safety guard ---
PAPER_TRADING_ONLY: bool = True

# --- Alpaca ---
ALPACA_API_KEY: str = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY: str = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL: str = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# --- News ---
NEWS_API_KEY: str = os.getenv("NEWS_API_KEY", "")

# --- Trading universe (~20 liquid large-caps) ---
UNIVERSE: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
    "META", "TSLA", "BRK-B", "JPM", "V",
    "UNH", "XOM", "JNJ", "PG", "MA",
    "HD", "AVGO", "MRK", "CVX", "PEP",
]

BENCHMARK: str = "SPY"

# --- Strategy parameters ---
MOMENTUM_LOOKBACK_DAYS: int = 90   # period over which to rank momentum
TOP_N: int = 5                      # number of positions to hold
REBALANCE_FREQUENCY: str = "weekly" # "daily" | "weekly" | "monthly"

# --- Position sizing ---
MAX_POSITION_PCT: float = 0.20  # max 20 % of portfolio in one name
CASH_BUFFER_PCT: float = 0.05   # keep 5 % cash at all times

# --- Risk controls ---
STOP_LOSS_PCT: float = 0.07     # exit if position falls 7 % from entry
MAX_DAILY_TRADES: int = 10

# --- Sentiment thresholds ---
SENTIMENT_VETO_NEGATIVE: float = 0.60  # veto trade if P(negative) > this

# --- Backtest defaults ---
BACKTEST_START: str = "2020-01-01"
BACKTEST_END: str = "2024-12-31"
BACKTEST_INITIAL_CASH: float = 500.0
BACKTEST_SLIPPAGE_PCT: float = 0.001  # 0.1 % per trade
