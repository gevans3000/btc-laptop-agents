from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from laptop_agents.trading.helpers import Candle, Tick


class ExchangeInterface(ABC):
    """
    Abstract Base Class for all broker/exchange implementations.
    Ensures that Live and Paper brokers are interchangeable.
    """

    @property
    @abstractmethod
    def symbol(self) -> str:
        """The trading symbol (e.g., BTCUSDT)."""
        pass

    @property
    @abstractmethod
    def pos(self) -> Optional[Any]:
        """The current open position snapshot."""
        pass

    @property
    @abstractmethod
    def current_equity(self) -> float:
        """Current account equity."""
        pass

    @abstractmethod
    def on_candle(
        self,
        candle: Candle,
        order: Optional[Dict[str, Any]],
        tick: Optional[Tick] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point for processing the close of a candle.
        Returns a dictionary of events (fills, exits, errors).
        """
        pass

    @abstractmethod
    def on_tick(self, tick: Tick) -> Dict[str, Any]:
        """
        Process a real-time price update.
        Used for sub-minute SL/TP monitoring.
        """
        pass

    @abstractmethod
    def place_order(
        self,
        *,
        side: str,
        qty: float,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit an order to the exchange/simulator."""
        pass

    @abstractmethod
    def get_unrealized_pnl(self, current_price: float) -> float:
        """Calculate current unrealized PnL."""
        pass

    @abstractmethod
    def close_all(self, exit_price: float) -> List[Dict[str, Any]]:
        """Emergency close of all positions."""
        pass

    @abstractmethod
    def cancel_all_open_orders(self) -> None:
        """Cancel all pending orders."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Graceful cleanup on session end."""
        pass
