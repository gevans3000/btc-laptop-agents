from __future__ import annotations

"""
State: Shared state object passed between agents in the pipeline.

Part of the Supervisor pipeline. See ENGINEER.md Section 4 for pipeline order.
"""

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
    trend: Dict[str, Any] = field(default_factory=dict)

    broker_events: Dict[str, Any] = field(default_factory=dict)

    trade_id: Optional[str] = None

    # lifecycle helpers
    pending_trigger_bars: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        from laptop_agents.constants import MAX_CANDLE_BUFFER

        if not isinstance(self.candles, list):
            self.candles = list(self.candles)

        # Enforce max buffer
        if len(self.candles) > MAX_CANDLE_BUFFER:
            self.candles = self.candles[-MAX_CANDLE_BUFFER:]
