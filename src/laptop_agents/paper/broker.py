from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
from ..core import hard_limits
import logging

logger = logging.getLogger(__name__)


@dataclass
class Position:
    side: str  # LONG / SHORT
    entry: float
    qty: float
    sl: float
    tp: float
    opened_at: str
    bars_open: int = 0
    trail_active: bool = False
    trail_stop: float = 0.0


class PaperBroker:
    """Very simple broker:
    - one position max
    - one TP + one SL
    - conservative intrabar resolution (stop-first if both touched)
    """

    def __init__(self, symbol: str = "BTCUSDT") -> None:
        self.pos: Optional[Position] = None
        self.is_inverse = symbol == "BTCUSD"

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

        # HARD LIMIT ENFORCEMENT
        notional = qty * fill_px
        if notional > hard_limits.MAX_POSITION_SIZE_USD:
            logger.warning(f"PAPER REJECTED: Notional ${notional:.2f} > hard limit ${hard_limits.MAX_POSITION_SIZE_USD}")
            return None
        
        # Check leverage - approximate using equity from order if provided
        equity = float(order.get("equity") or 10000.0)
        leverage = notional / equity
        if leverage > hard_limits.MAX_LEVERAGE:
             logger.warning(f"PAPER REJECTED: Leverage {leverage:.1f}x > hard limit {hard_limits.MAX_LEVERAGE}x")
             return None

        # For Inverse, we store 'qty' as Notional USD, but the input 'qty' is in Coins.
        # So we convert it here for the Position record.
        pos_qty = notional if self.is_inverse else qty
        
        self.pos = Position(side=side, entry=fill_px, qty=pos_qty, sl=sl, tp=tp, opened_at=candle.ts)
        return {"type": "fill", "side": side, "price": fill_px, "qty": pos_qty, "sl": sl, "tp": tp, "at": candle.ts}

    def _check_exit(self, candle: Any) -> Optional[Dict[str, Any]]:
        assert self.pos is not None
        p = self.pos

        # ATR Trailing Stop Logic (simplified: 1.5 ATR from highest close)
        atr_mult = 1.5  # Could be configurable
        if not p.trail_active:
            # Activate trail if profit > 0.5R
            if p.side == "LONG" and float(candle.close) > p.entry + abs(p.entry - p.sl) * 0.5:
                p.trail_active = True
                p.trail_stop = float(candle.close) - abs(p.entry - p.sl) * atr_mult
            elif p.side == "SHORT" and float(candle.close) < p.entry - abs(p.entry - p.sl) * 0.5:
                p.trail_active = True
                p.trail_stop = float(candle.close) + abs(p.entry - p.sl) * atr_mult
        else:
            # Update trail stop
            if p.side == "LONG":
                new_trail = float(candle.close) - abs(p.entry - p.sl) * atr_mult
                p.trail_stop = max(p.trail_stop, new_trail)
            else:
                new_trail = float(candle.close) + abs(p.entry - p.sl) * atr_mult
                p.trail_stop = min(p.trail_stop, new_trail)

            # Check trail hit
            if p.side == "LONG" and candle.low <= p.trail_stop:
                return self._exit(candle.ts, p.trail_stop, "TRAIL")
            elif p.side == "SHORT" and candle.high >= p.trail_stop:
                return self._exit(candle.ts, p.trail_stop, "TRAIL")

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
        
        if self.is_inverse:
            # Inverse PnL (BTC) = Notional * (1/Entry - 1/Exit) for Long
            if p.side == "LONG":
                pnl = p.qty * (1.0/p.entry - 1.0/px)
            else:
                pnl = p.qty * (1.0/px - 1.0/p.entry)
                
            # Inverse Risk (BTC) = Notional * |1/Entry - 1/SL|
            if p.side == "LONG":
                risk = p.qty * abs(1.0/p.entry - 1.0/p.sl)
            else:
                risk = p.qty * abs(1.0/p.sl - 1.0/p.entry)
        else:
            pnl = (px - p.entry) * p.qty if p.side == "LONG" else (p.entry - px) * p.qty
            risk = abs(p.entry - p.sl) * p.qty
            
        r_mult = (pnl / risk) if risk > 0 else 0.0
        return {"type": "exit", "reason": reason, "price": px, "pnl": pnl, "r": r_mult, "bars_open": p.bars_open, "at": ts}

    def get_unrealized_pnl(self, current_price: float) -> float:
        if self.pos is None:
            return 0.0
        p = self.pos
        
        if self.is_inverse:
             if p.side == "LONG":
                return p.qty * (1.0/p.entry - 1.0/current_price)
             else:
                return p.qty * (1.0/current_price - 1.0/p.entry)
        else:
            if p.side == "LONG":
                return (current_price - p.entry) * p.qty
            else:
                return (p.entry - current_price) * p.qty
