from __future__ import annotations

"""
CvdDivergenceAgent: Calculates synthetic CVD and detects divergences.

Part of the Supervisor pipeline. See ENGINEER.md Section 4 for pipeline order.
"""

from typing import Any, Dict, List
from .state import State
from ..indicators import Candle


class CvdDivergenceAgent:
    """Agent: Calculates synthetic CVD and detects divergences."""

    name = "cvd_divergence"

    def __init__(self, config: Dict[str, Any]) -> None:
        self.cfg = config
        self.lookback = config.get("lookback", 20)

    def run(self, state: State) -> State:
        candles = state.candles
        if len(candles) < self.lookback:
            return state

        # Calculate synthetic CVD
        cvd: List[float] = []
        current_cvd = 0.0
        for c in candles:
            range_len = c.high - c.low
            if range_len == 0:
                delta = 0.0
            else:
                # Bulls: (Close - Low), Bears: (High - Close)
                delta = ((c.close - c.low) - (c.high - c.close)) / range_len * c.volume
            current_cvd += delta
            cvd.append(current_cvd)

        state.cvd_divergence = {
            "cvd": cvd,
            "last_cvd": cvd[-1],
            "divergence": self._detect_divergence(candles, cvd),
        }
        return state

    def _detect_divergence(self, candles: List[Candle], cvd: List[float]) -> str:
        """Simple divergence detection."""
        if len(candles) < 5:
            return "NONE"

        # Check for Bullish Divergence (Price lower low, CVD higher low)
        # Check last 5 candles for local lows
        p_slice = [c.low for c in candles[-5:]]
        c_slice = cvd[-5:]

        # This is a very simplified check
        if p_slice[-1] < min(p_slice[:-1]) and c_slice[-1] > min(c_slice[:-1]):
            return "BULLISH"

        # Check for Bearish Divergence (Price higher high, CVD lower high)
        p_hi_slice = [c.high for c in candles[-5:]]
        if p_hi_slice[-1] > max(p_hi_slice[:-1]) and c_slice[-1] < max(c_slice[:-1]):
            return "BEARISH"

        return "NONE"
