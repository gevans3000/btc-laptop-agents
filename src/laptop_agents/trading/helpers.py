"""
Trading helpers extracted from run.py.
Phase 1 refactoring.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Candle:
    """OHLCV candle representation."""
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def sma(vals: List[float], window: int) -> Optional[float]:
    """Simple moving average over the last `window` values."""
    if len(vals) < window:
        return None
    return sum(vals[-window:]) / float(window)


def normalize_candle_order(candles: List[Candle]) -> List[Candle]:
    """
    Ensure candles are in chronological order (oldest first, newest last).
    Detects and fixes newest-first ordering that some providers return.
    """
    if len(candles) < 2:
        return candles
    
    # Parse timestamps for comparison
    first_ts = candles[0].ts
    last_ts = candles[-1].ts
    
    # Try to detect order by comparing timestamps
    # If first > last, reverse the list
    try:
        if first_ts > last_ts:
            return list(reversed(candles))
    except Exception:
        pass
    
    return candles
