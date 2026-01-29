"""WebSocket event dataclasses for Bitunix private channels."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class OrderEvent:
    """Order update event from Plan Order Channel."""

    order_id: str
    symbol: str
    side: str  # LONG, SHORT
    order_type: str  # MARKET, LIMIT
    status: str  # PENDING, FILLED, CANCELLED, REJECTED
    qty: float
    price: Optional[float]
    filled_qty: float
    avg_fill_price: Optional[float]
    timestamp: str
    raw: dict  # Original payload for debugging


@dataclass
class PositionEvent:
    """Position update event from Position Channel."""

    position_id: str
    symbol: str
    side: str  # LONG, SHORT
    qty: float
    entry_price: float
    unrealized_pnl: float
    timestamp: str
    raw: dict  # Original payload for debugging
