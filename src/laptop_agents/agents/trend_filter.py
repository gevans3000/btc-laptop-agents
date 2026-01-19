from __future__ import annotations
from .state import State


class TrendFilterAgent:
    """Filter trades against higher timeframe trend."""

    name = "trend_filter"

    def __init__(self, higher_tf_candles: int = 4):
        self.htf_candles = higher_tf_candles

    def run(self, state: State) -> State:
        if len(state.candles) < self.htf_candles * 60:  # 4H = 240 1m candles
            return state

        # Simple trend: compare current to 4H ago
        current = state.candles[-1].close
        htf_ago = state.candles[-(self.htf_candles * 60)].close

        trend = "UP" if current > htf_ago else "DOWN"
        state.trend = {"direction": trend, "strength": abs(current - htf_ago) / htf_ago}

        # Block counter-trend trades
        order = state.order
        if order and order.get("go"):
            side = order.get("side")
            if (trend == "DOWN" and side == "LONG") or (
                trend == "UP" and side == "SHORT"
            ):
                state.order = {"go": False, "reason": f"counter_trend_{trend}"}

        return state
