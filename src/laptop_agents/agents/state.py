from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..indicators import Candle


@dataclass
class State:
    instrument: str = "BTCUSDT"
    timeframe: str = "5m"

    candles: List[Candle] = field(default_factory=list)

    market_context: Dict[str, Any] = field(default_factory=dict)
    derivatives: Dict[str, Any] = field(default_factory=dict)

    setup: Dict[str, Any] = field(default_factory=dict)
    cvd_divergence: Dict[str, Any] = field(default_factory=dict)
    order: Dict[str, Any] = field(default_factory=dict)

    broker_events: Dict[str, Any] = field(default_factory=dict)

    trade_id: Optional[str] = None

    # lifecycle helpers
    pending_trigger_bars: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)
