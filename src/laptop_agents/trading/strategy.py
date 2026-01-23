from __future__ import annotations
from typing import List, Optional
from abc import ABC, abstractmethod
from laptop_agents.trading.helpers import Candle, sma
from laptop_agents.indicators import atr


class BaseStrategy(ABC):
    @abstractmethod
    def generate_signal(self, candles: List[Candle]) -> Optional[str]:
        pass


class SMACrossoverStrategy(BaseStrategy):
    def __init__(
        self,
        fast_period: int = 10,
        slow_period: int = 30,
        volatility_filter: bool = True,
    ):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.volatility_filter = volatility_filter

    def generate_signal(self, candles: List[Candle]) -> Optional[str]:
        if not candles or len(candles) < max(self.fast_period, self.slow_period):
            return None

        closes = [float(c.close) for c in candles]
        fast_sma = sma(closes, self.fast_period)
        slow_sma = sma(closes, self.slow_period)

        if fast_sma is None or slow_sma is None:
            return None

        if self.volatility_filter:
            # ATR Volatility Filter
            current_close = closes[-1]
            a = atr(candles, 14)
            if a is not None:
                volatility_ratio = a / current_close
                if volatility_ratio < 0.005:
                    return None

        if fast_sma > slow_sma:
            return "BUY"
        else:
            return "SELL"
