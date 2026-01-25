from __future__ import annotations
from typing import Any, Dict, List, Optional
from laptop_agents.paper.broker_types import Position
from laptop_agents.paper.position_engine import (
    calculate_unrealized_pnl,
    calculate_full_exit_pnl,
)
import uuid
from collections import deque
from datetime import datetime, timezone


class BacktestBroker:
    """In-memory broker for backtesting.
    Unifies logic with PaperBroker but simplified for speed and deterministic testing.
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        fees_bps: float = 0.0,
        starting_equity: float = 10000.0,
        random_seed: Optional[int] = None,
        strategy_config: Optional[Dict[str, Any]] = None,
        fill_simulator_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.symbol = symbol
        self.strategy_config = strategy_config or {}
        self.pos: Optional[Position] = None
        self.is_inverse = self.symbol.endswith("USD") and not self.symbol.endswith(
            "USDT"
        )

        self.starting_equity = starting_equity
        self.current_equity = starting_equity

        # Simple fee model
        self.exchange_fees = {
            "maker": fees_bps / 10000.0,
            "taker": fees_bps / 10000.0,
        }

        from laptop_agents.backtest.fill_simulator import FillSimulator

        self.simulator = FillSimulator(
            fill_simulator_config or {"random_seed": random_seed}
        )

        self.order_history: List[Dict[str, Any]] = []
        self.processed_order_ids: set[str] = set()

    def on_candle(
        self, candle: Any, order: Optional[Dict[str, Any]], tick: Optional[Any] = None
    ) -> Dict[str, Any]:
        events: Dict[str, Any] = {"fills": [], "exits": []}

        # 1) Manage open position
        if self.pos is not None:
            self.pos.bars_open += 1
            exit_event = self._check_exit(candle)
            if exit_event:
                events["exits"].append(exit_event)
                self.pos = None

        # 2) Open new position if none
        if self.pos is None and order and order.get("go"):
            fill = self._try_fill(candle, order)
            if fill:
                events["fills"].append(fill)

        return events

    def on_tick(self, tick: Any) -> Dict[str, Any]:
        """No-op for backtest as we assume candle-level resolution mostly."""
        return {"exits": []}

    def _try_fill(self, candle: Any, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.simulator.should_fill(order, candle):
            return None

        client_order_id = order.get("client_order_id") or uuid.uuid4().hex
        side = order["side"]
        qty = float(order["qty"])
        entry_type = order.get("entry_type", "market")
        entry = float(order.get("entry", 0.0))
        sl = float(order.get("sl", 0.0))
        tp = float(order.get("tp", 0.0))

        if entry_type == "market":
            fill_px = float(candle.close)
        else:
            fill_px = entry

        # Realistic slippage
        fill_px = self.simulator.apply_slippage(fill_px, side, is_entry=True)

        fee_rate = self.exchange_fees["taker"]
        notional = qty * fill_px
        fees = notional * fee_rate

        pos_qty = notional if self.is_inverse else qty
        trade_id = client_order_id

        new_lot = {"qty": pos_qty, "price": fill_px, "fees": fees}

        if self.pos:
            # Add to existing position if same side, else ignore for now or handle reversal
            if side == self.pos.side:
                self.pos.lots.append(new_lot)
                self.pos.qty += pos_qty
            else:
                # Close existing first? For simplicity in MVP backtest, we assume no concurrent opposite positions
                # This could be improved to handle FIFO closures of opposite positions
                return None
        else:
            self.pos = Position(
                side=side,
                qty=pos_qty,
                sl=sl,
                tp=tp,
                opened_at=str(candle.ts),
                lots=deque([new_lot]),
                trade_id=trade_id,
            )

        fill_event = {
            "type": "fill",
            "trade_id": trade_id,
            "side": side,
            "price": fill_px,
            "qty": pos_qty,
            "sl": sl,
            "tp": tp,
            "at": str(candle.ts),
            "fees": fees,
        }
        self.order_history.append(fill_event)
        return fill_event

    def _check_exit(self, candle: Any) -> Optional[Dict[str, Any]]:
        assert self.pos is not None
        p = self.pos

        # SL/TP checks
        if p.side == "LONG":
            sl_hit = candle.low <= p.sl
            tp_hit = candle.high >= p.tp
            if sl_hit:
                return self._exit(str(candle.ts), p.sl, "SL")
            if tp_hit:
                return self._exit(str(candle.ts), p.tp, "TP")
        else:
            sl_hit = candle.high >= p.sl
            tp_hit = candle.low <= p.tp
            if sl_hit:
                return self._exit(str(candle.ts), p.sl, "SL")
            if tp_hit:
                return self._exit(str(candle.ts), p.tp, "TP")
        return None

    def _exit(self, ts: str, px: float, reason: str) -> Dict[str, Any]:
        assert self.pos is not None
        p = self.pos

        # Apply slippage on exit
        px_slipped = self.simulator.apply_slippage(px, p.side, is_entry=False)

        exit_fee_rate = self.exchange_fees["taker"]
        results = calculate_full_exit_pnl(p, px_slipped, exit_fee_rate, self.is_inverse)

        net_pnl = results["net_pnl"]
        self.current_equity += net_pnl

        exit_event = {
            "type": "exit",
            "trade_id": p.trade_id,
            "reason": reason,
            "entry": float(results["avg_entry"]),
            "exit": float(px),
            "price": float(px),
            "qty": float(p.qty),
            "pnl": float(net_pnl),
            "at": ts,
            "fees": float(results["total_fees"]),
            "side": p.side,
        }
        self.order_history.append(exit_event)
        return exit_event

    def get_unrealized_pnl(self, current_price: float) -> float:
        return calculate_unrealized_pnl(self.pos, current_price, self.is_inverse)

    def shutdown(self) -> None:
        pass

    def save_state(self) -> None:
        pass

    def close_all(self, current_price: float) -> List[Dict[str, Any]]:
        if self.pos is None:
            return []
        exit_event = self._exit(
            datetime.now(timezone.utc).isoformat(), current_price, "FORCE_CLOSE"
        )
        self.pos = None
        return [exit_event]
