"""
Central configuration.
"""
import json
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
FINNHUB_API_KEY: str = os.getenv("FINNHUB_API_KEY", "")
NEWSAPI_KEY: str = os.getenv("NEWSAPI_KEY", "")

# --- LM Studio (local LLM sentiment scorer) ---
# Set LM_STUDIO_URL in .env to point at whichever machine is running LM Studio
# Default assumes it is running on the same machine
LM_STUDIO_URL: str = os.getenv("LM_STUDIO_URL", "http://localhost:1234")

# --- Trading universe ---
# Loads from data/sp500_tickers.json if present (run scripts/update_universe.py to generate).
# Falls back to a 20-stock large-cap list if the file doesn't exist yet.
_SP500_PATH = DATA_DIR / "sp500_tickers.json"

def _load_universe() -> list[str]:
    if _SP500_PATH.exists():
        with open(_SP500_PATH) as f:
            tickers = json.load(f)
        return tickers
    # Fallback: 20 liquid large-caps
    return [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
        "META", "TSLA", "BRK-B", "JPM", "V",
        "UNH", "XOM", "JNJ", "PG", "MA",
        "HD", "AVGO", "MRK", "CVX", "PEP",
    ]

UNIVERSE: list[str] = _load_universe()

BENCHMARK: str = "SPY"

# --- Strategy parameters ---
MOMENTUM_LOOKBACK_DAYS: int = 90   # period over which to rank momentum
TOP_N: int = 5                      # number of positions to hold
MOMENTUM_BUFFER: int = 0            # hold existing positions until they fall outside top N+buffer (0 = off, try 3+ with larger universes)
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
BACKTEST_START: str = "2019-01-01"
BACKTEST_END: str = "2024-12-31"
BACKTEST_INITIAL_CASH: float = 100_000.0
BACKTEST_SLIPPAGE_PCT: float = 0.001  # 0.1 % per trade
