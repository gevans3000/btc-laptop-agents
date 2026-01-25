from __future__ import annotations
from typing import Any, Dict
import random


class FillSimulator:
    """Simulates realistic order fills during backtesting."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.slippage_model = config.get("slippage_model", "fixed_bps")
        self.slippage_bps = float(config.get("slippage_bps", 2.0))
        self.spread_bps = float(config.get("spread_bps", 1.0))
        self.latency_ms = int(config.get("latency_ms", 0))
        self.rng = random.Random(config.get("random_seed"))

    def apply_slippage(self, price: float, side: str, is_entry: bool) -> float:
        """Apply slippage based on the configured model."""
        if self.slippage_model == "fixed_bps":
            factor = self.slippage_bps
        elif self.slippage_model == "random":
            # 0.5x to 1.5x of base bps
            factor = self.slippage_bps * self.rng.uniform(0.5, 1.5)
        else:
            factor = self.slippage_bps

        rate = factor / 10000.0
        if side == "LONG":
            # Entry: Buy higher, Exit: Sell lower
            return price * (1.0 + rate) if is_entry else price * (1.0 - rate)
        else:
            # Entry: Sell lower, Exit: Buy higher
            return price * (1.0 - rate) if is_entry else price * (1.0 + rate)

    def should_fill(self, order: Dict[str, Any], candle: Any) -> bool:
        """For limit orders: check if price was touched."""
        entry_type = order.get("entry_type", "market")
        if entry_type == "market":
            return True

        entry = float(order.get("entry", 0))
        # Conservatively check if high/low touched
        return candle.low <= entry <= candle.high
