"""
MarketIntakeAgent: Handles market data intake and indicator calculation.

Part of the Supervisor pipeline. See ENGINEER.md Section 4 for pipeline order.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any

from ..indicators import ema, atr, swing_high_low, equal_level
from .state import State


class MarketIntakeAgent:
    """Agent 1 — Market Intake: structure, levels, regime, what changed."""

    name = "market_intake"

    def __init__(self) -> None:
        self.overrides: Dict[str, Any] = {}
        ov_path = Path("config/symbol_overrides.json")
        if ov_path.exists():
            try:
                with ov_path.open("r") as f:
                    self.overrides = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(f"FAILED TO LOAD symbol_overrides.json: {e}")

    def run(self, state: State) -> State:
        candles = state.candles
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        last = closes[-1]

        ema_fast = ema(closes, 20)
        ema_slow = ema(closes, 50)

        trend = "UNKNOWN"
        if ema_fast and ema_slow:
            if ema_fast > ema_slow and last > ema_fast:
                trend = "UP"
            elif ema_fast < ema_slow and last < ema_fast:
                trend = "DOWN"
            else:
                trend = "CHOP"

        a = atr(candles, 14)
        atr_pct = (a / last) if a else None
        if atr_pct is None:
            regime = "UNKNOWN"
        elif atr_pct < 0.002:
            regime = "CHOP_LOWVOL"
        elif atr_pct > 0.006:
            regime = "TREND_HIGHVOL"
        else:
            regime = "NORMAL"

        swing_hi, swing_lo = swing_high_low(candles, lookback=40)

        # Get symbol-specific tolerance
        symbol = state.instrument
        tol = self.overrides.get(symbol, {}).get("eq_tolerance_pct", 0.0008)

        eq_high = equal_level(highs, tol_pct=tol)
        eq_low = equal_level(lows, tol_pct=tol)

        bullets: List[str] = []
        bullets.append(f"Trend={trend} Regime={regime}")
        if swing_hi and swing_lo:
            bullets.append(f"Swing range: {swing_lo:,.0f} → {swing_hi:,.0f}")
        if eq_high:
            bullets.append(f"Equal-highs zone ~{eq_high:,.0f}")
        if eq_low:
            bullets.append(f"Equal-lows zone ~{eq_low:,.0f}")

        state.market_context = {
            "price": last,
            "trend": trend,
            "regime": regime,
            "ema20": ema_fast,
            "ema50": ema_slow,
            "swing_high": swing_hi,
            "swing_low": swing_lo,
            "eq_high": eq_high,
            "eq_low": eq_low,
            "bullets": bullets[-5:],
            "atr": a,
            "atr_pct": atr_pct,
        }
        return state
