"""
Base class defining the screener contract.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass
class ScreenerPick:
    ticker: str
    score: float   # higher = stronger signal
    reason: str    # human-readable explanation of the score


class BaseScreener(ABC):
    @abstractmethod
    def screen(self, prices: dict[str, pd.DataFrame]) -> list[ScreenerPick]:
        """Return picks sorted by score descending (best first)."""
