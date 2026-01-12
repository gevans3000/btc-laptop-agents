from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple
import math


@dataclass(frozen=True)
class Candle:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def ema(values: List[float], period: int) -> Optional[float]:
    if period <= 0 or len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = (v - e) * k + e
    return e


def true_range(prev_close: float, high: float, low: float) -> float:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def atr(candles: List[Candle], period: int = 14) -> Optional[float]:
    if len(candles) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(candles)):
        trs.append(true_range(candles[i-1].close, candles[i].high, candles[i].low))
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def swing_high_low(candles: List[Candle], lookback: int = 40) -> Tuple[Optional[float], Optional[float]]:
    if not candles:
        return None, None
    window = candles[-lookback:] if len(candles) >= lookback else candles
    hi = max(c.high for c in window)
    lo = min(c.low for c in window)
    return hi, lo


def equal_level(values: List[float], tol_pct: float = 0.0008) -> Optional[float]:
    """Return a level if at least 2 recent values cluster within tolerance."""
    if len(values) < 6:
        return None
    recent = values[-12:]
    # compare last value to earlier values in recent window
    last = recent[-1]
    tol = abs(last) * tol_pct
    matches = [v for v in recent[:-1] if abs(v - last) <= tol]
    if len(matches) >= 1:
        # average cluster
        return (sum(matches) + last) / (len(matches) + 1)
    return None


def vwap(candles: List[Candle]) -> List[float]:
    """Calculate Volume Weighted Average Price."""
    if not candles:
        return []
    
    vwap_values = []
    cum_pv = 0.0
    cum_vol = 0.0
    
    # Simple VWAP (resetting could be done by period or daily, 
    # but for 1m scalping we often use the visible window or session)
    for c in candles:
        typical_price = (c.high + c.low + c.close) / 3.0
        cum_pv += typical_price * c.volume
        cum_vol += c.volume
        if cum_vol == 0:
            vwap_values.append(c.close)
        else:
            vwap_values.append(cum_pv / cum_vol)
    return vwap_values


def detect_sweep(candles: List[Candle], level: float, side: str, lookback: int = 5) -> bool:
    """
    Detect if price swept a level and returned.
    side: 'LONG' (swept low), 'SHORT' (swept high)
    """
    if len(candles) < 2:
        return False
    
    last = candles[-1]
    prev = candles[-2]
    
    if side == "LONG":
        # Swept low: previous low was below level (or current low is) 
        # but current close is above level.
        swept = any(c.low < level for c in candles[-lookback:])
        reclaimed = last.close > level
        # Also ensure we didn't just crash through
        return swept and reclaimed and last.close > prev.close
    else:
        # Swept high: previous high was above level
        # but current close is below level
        swept = any(c.high > level for c in candles[-lookback:])
        reclaimed = last.close < level
        return swept and reclaimed and last.close < prev.close
