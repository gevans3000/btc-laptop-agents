from dataclasses import dataclass
from typing import Optional


@dataclass
class Candle:
    close: float
    high: float
    low: float
    volume: float


def ema(values: list[float], period: int) -> Optional[float]:
    if period <= 0 or len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = (v - e) * k + e
    return e


def ema_momentum_signal(closes: list[float], fast: int = 9, slow: int = 21) -> tuple[float, str]:
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    if fast_ema is None or slow_ema is None:
        return 0.0, "neutral"
    diff = (fast_ema - slow_ema) / slow_ema if slow_ema else 0.0
    if diff > 0.002:
        return diff, "bullish"
    if diff < -0.002:
        return diff, "bearish"
    return diff, "neutral"
