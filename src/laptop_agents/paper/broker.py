from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass
class Position:
    side: str  # LONG / SHORT
    entry: float
    qty: float
    sl: float
    tp: float
    opened_at: str
    bars_open: int = 0


class PaperBroker:
    """Very simple broker:
    - one position max
    - one TP + one SL
    - conservative intrabar resolution (stop-first if both touched)
    """

    def __init__(self) -> None:
        self.pos: Optional[Position] = None

    def on_candle(self, candle: Any, order: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        events: Dict[str, Any] = {"fills": [], "exits": []}

        # 1) manage open position
        if self.pos is not None:
            self.pos.bars_open += 1
            exit_event = self._check_exit(candle)
            if exit_event:
                events["exits"].append(exit_event)
                self.pos = None

        # 2) open new position if none
        if self.pos is None and order and order.get("go"):
            fill = self._try_fill(candle, order)
            if fill:
                events["fills"].append(fill)

        return events

    def _try_fill(self, candle: Any, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        entry_type = order["entry_type"]  # "limit" or "market"
        entry = float(order["entry"])
        side = order["side"]
        qty = float(order["qty"])
        sl = float(order["sl"])
        tp = float(order["tp"])

        if entry_type == "market":
            fill_px = float(candle.close)
        else:
            # limit fill if touched
            if not (candle.low <= entry <= candle.high):
                return None
            fill_px = entry

        self.pos = Position(side=side, entry=fill_px, qty=qty, sl=sl, tp=tp, opened_at=candle.ts)
        return {"type": "fill", "side": side, "price": fill_px, "qty": qty, "sl": sl, "tp": tp, "at": candle.ts}

    def _check_exit(self, candle: Any) -> Optional[Dict[str, Any]]:
        assert self.pos is not None
        p = self.pos

        if p.side == "LONG":
            sl_hit = candle.low <= p.sl
            tp_hit = candle.high >= p.tp
            if sl_hit and tp_hit:
                # conservative: assume stop first
                return self._exit(candle.ts, p.sl, "SL_conservative")
            if sl_hit:
                return self._exit(candle.ts, p.sl, "SL")
            if tp_hit:
                return self._exit(candle.ts, p.tp, "TP")
        else:  # SHORT
            sl_hit = candle.high >= p.sl
            tp_hit = candle.low <= p.tp
            if sl_hit and tp_hit:
                return self._exit(candle.ts, p.sl, "SL_conservative")
            if sl_hit:
                return self._exit(candle.ts, p.sl, "SL")
            if tp_hit:
                return self._exit(candle.ts, p.tp, "TP")

        return None

    def _exit(self, ts: str, px: float, reason: str) -> Dict[str, Any]:
        assert self.pos is not None
        p = self.pos
        pnl = (px - p.entry) * p.qty if p.side == "LONG" else (p.entry - px) * p.qty
        risk = abs(p.entry - p.sl) * p.qty
        r_mult = (pnl / risk) if risk > 0 else 0.0
        return {"type": "exit", "reason": reason, "price": px, "pnl": pnl, "r": r_mult, "bars_open": p.bars_open, "at": ts}
