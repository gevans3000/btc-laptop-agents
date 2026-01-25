"""Protocol definitions for dependency injection."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class BrokerProtocol(Protocol):
    """Interface for all broker implementations (Paper, Live, Dry-Run)."""

    symbol: str
    current_equity: float
    is_inverse: bool

    def on_candle(
        self,
        candle: Any,
        order: Optional[Dict[str, Any]],
        tick: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Process a candle and optional order, return events dict with fills/exits/errors."""
        ...

    def on_tick(self, tick: Any) -> Dict[str, Any]:
        """Process a real-time tick for position monitoring."""
        ...

    def get_unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized PnL at given price."""
        ...

    def shutdown(self) -> None:
        """Graceful shutdown, cancel orders, save state."""
        ...

    def save_state(self) -> None:
        """Persist current state to disk."""
        ...

    def close_all(self, current_price: float) -> List[Dict[str, Any]]:
        """Emergency close all positions."""
        ...
