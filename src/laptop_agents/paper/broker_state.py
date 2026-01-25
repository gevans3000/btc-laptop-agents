"""State persistence mixin for PaperBroker."""

from __future__ import annotations
import time
from collections import deque
from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING

from .broker_types import Position
from laptop_agents.core.logger import logger
from laptop_agents.core.config import load_risk_limits, get_repo_root, load_yaml_config
from laptop_agents.resilience.exceptions import PersistenceError

if TYPE_CHECKING:
    from ..storage.position_store import PositionStore


class BrokerStateInterface(Protocol):
    symbol: str
    starting_equity: float
    current_equity: float
    processed_order_ids: set[str]
    order_history: List[Dict[str, Any]]
    working_orders: List[Dict[str, Any]]
    pos: Optional[Position]
    state_path: Optional[str]
    store: Optional[PositionStore]
    exchange_fees: Dict[str, float]
    max_position_per_symbol: Dict[str, float]


class BrokerStateMixin:
    """Mixin for PaperBroker to handle saving/loading state and config."""

    symbol: str
    starting_equity: float
    current_equity: float
    processed_order_ids: set[str]
    order_history: List[Dict[str, Any]]
    working_orders: List[Dict[str, Any]]
    pos: Optional[Position]
    state_path: Optional[str]
    store: Optional[PositionStore]
    exchange_fees: Dict[str, float]
    max_position_per_symbol: Dict[str, float]

    def _save_state(self: Any) -> None:
        if not hasattr(self, "store") or not self.store:
            return

        state = {
            "symbol": self.symbol,
            "starting_equity": self.starting_equity,
            "current_equity": self.current_equity,
            "processed_order_ids": list(self.processed_order_ids),
            "order_history": self.order_history,
            "working_orders": self.working_orders,
            "pos": None,
            "saved_at": time.time(),
        }
        if self.pos:
            state["pos"] = {
                "side": self.pos.side,
                "entry": self.pos.entry,
                "qty": self.pos.qty,
                "sl": self.pos.sl,
                "tp": self.pos.tp,
                "opened_at": self.pos.opened_at,
                "lots": list(self.pos.lots),
                "bars_open": self.pos.bars_open,
                "trail_active": self.pos.trail_active,
                "trail_stop": self.pos.trail_stop,
            }

        self.store.save_state(self.symbol, state)

    def _load_state(self: Any) -> None:
        if not hasattr(self, "store") or not self.store:
            return

        state = self.store.load_state(self.symbol)
        if not state:
            logger.info("No existing state found in DB. Starting fresh.")
            return

        try:
            self.starting_equity = state.get("starting_equity", self.starting_equity)
            self.current_equity = state.get("current_equity", self.current_equity)
            self.processed_order_ids = set(state.get("processed_order_ids", []))
            self.order_history = state.get("order_history", [])
            self.working_orders = state.get("working_orders", [])

            # Expire stale working orders (> 24 hours old)
            now = time.time()
            original_count = len(self.working_orders)
            self.working_orders = [
                o for o in self.working_orders if now - o.get("created_at", now) < 86400
            ]  # 24 hours
            if original_count != len(self.working_orders):
                logger.info(
                    f"Expired {original_count - len(self.working_orders)} stale working orders"
                )

            pos_data = state.get("pos")
            if pos_data:
                # Convert lots back to deque
                if "lots" in pos_data:
                    pos_data["lots"] = deque(pos_data["lots"])
                else:
                    # Migration for old state
                    old_lot = {
                        "qty": pos_data.get("qty", 0),
                        "price": pos_data.get("entry", 0),
                        "fees": pos_data.get("entry_fees", 0),
                    }
                    pos_data["lots"] = deque([old_lot])

                # Clean up keys that Position dataclass doesn't expect
                filtered_pos = {
                    k: v
                    for k, v in pos_data.items()
                    if k not in ["entry", "entry_fees"]
                }
                self.pos = Position(**filtered_pos)

            logger.info(f"Loaded broker state from DB: {self.state_path}")

        except Exception as e:
            raise PersistenceError(f"Failed to load broker state: {e}") from e

    def _load_risk_config(self: Any) -> None:
        """Load risk settings from config/risk.yaml."""
        config = load_risk_limits()
        if config and "max_position_per_symbol" in config:
            self.max_position_per_symbol = config["max_position_per_symbol"]
            logger.info(f"Loaded risk config: {self.max_position_per_symbol}")

    def _load_exchange_config(self: Any) -> None:
        """Load exchange fees from config/exchanges/bitunix.yaml."""
        config_path = get_repo_root() / "config" / "exchanges" / "bitunix.yaml"
        config = load_yaml_config(config_path)
        if config and "fees" in config:
            self.exchange_fees = config["fees"]
            logger.info(f"Loaded exchange fees: {self.exchange_fees}")
