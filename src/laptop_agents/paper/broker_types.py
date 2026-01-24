"""Types for PaperBroker."""

from __future__ import annotations
from dataclasses import dataclass
from collections import deque
from typing import Any, Dict


@dataclass
class Position:
    side: str  # LONG / SHORT
    qty: float
    sl: float
    tp: float
    opened_at: str
    lots: deque[
        Dict[str, Any]
    ]  # FIFO lots: {"qty": float, "price": float, "fees": float}
    trade_id: str = ""
    bars_open: int = 0
    trail_active: bool = False
    trail_stop: float = 0.0

    @property
    def entry(self) -> float:
        """Average entry price of all lots."""
        if not self.lots:
            return 0.0
        total_qty = sum(lot["qty"] for lot in self.lots)
        if total_qty == 0:
            return 0.0
        return sum(lot["qty"] * lot["price"] for lot in self.lots) / total_qty

    @property
    def entry_fees(self) -> float:
        return sum(lot["fees"] for lot in self.lots)
