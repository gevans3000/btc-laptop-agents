from __future__ import annotations


from typing import Any, Dict, List, Optional, Tuple
from laptop_agents.trading.helpers import Candle


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
        trs.append(true_range(candles[i - 1].close, candles[i].high, candles[i].low))
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period


def swing_high_low(
    candles: List[Candle], lookback: int = 40
) -> Tuple[Optional[float], Optional[float]]:
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

    for c in candles:
        typical_price = (c.high + c.low + c.close) / 3.0
        cum_pv += typical_price * c.volume
        cum_vol += c.volume
        if cum_vol == 0:
            vwap_values.append(c.close)
        else:
            vwap_values.append(cum_pv / cum_vol)
    return vwap_values


def cvd_indicator(candles: List[Candle]) -> List[float]:
    """Calculate synthetic Cumulative Volume Delta."""
    cvd = []
    current_cvd = 0.0
    for c in candles:
        range_len = c.high - c.low
        if range_len == 0:
            delta = 0.0
        else:
            delta = ((c.close - c.low) - (c.high - c.close)) / range_len * c.volume
        current_cvd += delta
        cvd.append(current_cvd)
    return cvd


def detect_sweep(candles: List[Candle], lookback: int = 10) -> Dict[str, Any]:
    """
    Detect if the LAST candle swept a recent swing and reclaimed.
    Returns: {"swept": "HIGH"|"LOW"|None, "level": float|None, "reclaimed": bool}
    """
    if len(candles) < lookback + 1:
        return {"swept": None, "level": None, "reclaimed": False}

    window = candles[-(lookback + 1) : -1]
    curr = candles[-1]

    swing_high = max(c.high for c in window)
    swing_low = min(c.low for c in window)

    if curr.high > swing_high and curr.close < swing_high:
        return {"swept": "HIGH", "level": swing_high, "reclaimed": True}

    if curr.low < swing_low and curr.close > swing_low:
        return {"swept": "LOW", "level": swing_low, "reclaimed": True}

    return {"swept": None, "level": None, "reclaimed": False}
