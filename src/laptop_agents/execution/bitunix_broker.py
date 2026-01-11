"""
Bitunix Live Broker - Real execution bridge for Bitunix Futures.
Syncs local state with exchange positions and handles order submission.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from ..data.providers.bitunix_futures import BitunixFuturesProvider
from ..resilience.errors import SafetyException
from ..core import hard_limits
import os

logger = logging.getLogger(__name__)

class BitunixBroker:
    """
    Real-world broker implementation for Bitunix.
    Polls position state to synthesize fill/exit events.
    """

    def __init__(self, provider: BitunixFuturesProvider):
        self.provider = provider
        self.symbol = provider.symbol
        self.last_pos: Optional[Dict[str, Any]] = None
        self._initialized = False
        self._instrument_info: Optional[Dict[str, Any]] = None

    def _get_info(self) -> Dict[str, Any]:
        if self._instrument_info is None:
            self._instrument_info = self.provider.fetch_instrument_info(self.symbol)
        return self._instrument_info

    def _round_step(self, val: float, step: float) -> float:
        if not step or step <= 0:
            return val
        return round(round(val / step) * step, 8)

    def on_candle(self, candle: Any, order: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        1. Submits new orders if order['go'] is True.
        2. Polls exchange for position status.
        3. Synthesizes fill/exit events by diffing state.
        """
        events: Dict[str, Any] = {"fills": [], "exits": [], "errors": []}

        # 0) Kill Switch Check
        if os.path.exists("config/KILL_SWITCH.txt"):
            with open("config/KILL_SWITCH.txt", "r") as f:
                if "TRUE" in f.read().upper():
                    logger.warning("KILL SWITCH DETECTED! Blocking all orders.")
                    return {"fills": [], "exits": [], "errors": ["KILL_SWITCH_ACTIVE"]}

        # 1) Handle New Order (Submit to exchange)
        if order and order.get("go"):
            try:
                # We only submit if we don't think we have a position already 
                if not self.last_pos:
                    info = self._get_info()
                    qty = self._round_step(float(order["qty"]), info["lotSize"])
                    px = self._round_step(float(order["entry"]), info["tickSize"]) if order.get("entry") else float(candle.close)
                    
                    # HARD LIMIT ENFORCEMENT
                    notional = qty * px
                    if notional > hard_limits.MAX_POSITION_SIZE_USD:
                        msg = f"REJECTED: Order notional ${notional:.2f} exceeds hard limit ${hard_limits.MAX_POSITION_SIZE_USD}"
                        logger.error(msg)
                        raise SafetyException(msg)
                    
                    sl = self._round_step(float(order["sl"]), info["tickSize"]) if order.get("sl") else None
                    tp = self._round_step(float(order["tp"]), info["tickSize"]) if order.get("tp") else None

                    logger.info(f"Submitting LIVE order: {order} (Rounded: qty={qty}, px={px}, sl={sl}, tp={tp})")
                    resp = self.provider.place_order(
                        side=order["side"],
                        qty=qty,
                        order_type=order.get("entry_type", "MARKET").upper(),
                        price=px,
                        sl_price=sl,
                        tp_price=tp
                    )
                    events["order_submission"] = resp
            except SafetyException as e:
                events["errors"].append(str(e))
            except Exception as e:
                logger.error(f"Live order submission failed: {e}")
                events["errors"].append(str(e))

        # 2) Sync State (Poll Position)
        try:
            current_positions = self.provider.get_pending_positions(self.symbol)
            # Find position for our symbol
            # Usually Bitunix returns a list of positions. 
            # We look for the one matching self.symbol.
            current_pos = None
            for p in current_positions:
                # Defensive check on field names - Bitunix docs vary
                p_sym = p.get("symbol") or p.get("symbolName")
                if p_sym == self.symbol:
                    # Filter out zero positions if exchange returns them
                    qty = float(p.get("qty") or p.get("positionAmount") or 0)
                    if abs(qty) > 0:
                        current_pos = p
                        break
            
            # DRIFT DETECTION
            last_qty = float(self.last_pos.get("qty") or self.last_pos.get("positionAmount") or 0) if self.last_pos else 0.0
            curr_qty = float(current_pos.get("qty") or current_pos.get("positionAmount") or 0) if current_pos else 0.0
            
            if abs(last_qty - curr_qty) > 0.00000001:
                # If we didn't expect a fill/exit but the qty changed, it's a drift
                if not events["fills"] and not events["exits"] and self._initialized:
                     logger.warning(f"STATE DRIFT DETECTED: Internal={last_qty}, Exchange={curr_qty}. Snapping to exchange.")
            
            # 3) Synthesize Events
            if not self._initialized:
                # First run - just establish baseline
                self.last_pos = current_pos
                self._initialized = True
                return events

            # Case: No pos -> Pos (FILL)
            if not self.last_pos and current_pos:
                qty = float(current_pos.get("qty") or current_pos.get("positionAmount") or 0)
                px = float(current_pos.get("entryPrice") or current_pos.get("avgPrice") or 0)
                side = current_pos.get("side") or ("LONG" if qty > 0 else "SHORT")
                
                fill_event = {
                    "type": "fill",
                    "side": side,
                    "price": px,
                    "qty": abs(qty),
                    "at": candle.ts,
                    "exchange_id": current_pos.get("positionId")
                }
                events["fills"].append(fill_event)
                logger.info(f"LIVE Fill Detected: {fill_event}")

            # Case: Pos -> No pos (EXIT)
            elif self.last_pos and not current_pos:
                # We don't have the exit price from the position list (it's gone)
                # In a robust system we'd poll order history, but for MVP 
                # we'll use candle close as a proxy or just report the exit.
                px = float(candle.close) 
                
                exit_event = {
                    "type": "exit",
                    "reason": "exchange_detected",
                    "price": px,
                    "pnl": 0.0, # Will be reconciled by journal/equity check if needed
                    "at": candle.ts
                }
                events["exits"].append(exit_event)
                logger.info(f"LIVE Exit Detected: {exit_event}")

            self.last_pos = current_pos

        except Exception as e:
            logger.error(f"Live position sync failed: {e}")
            events["errors"].append(str(e))

        return events

    def get_unrealized_pnl(self, current_price: float) -> float:
        """Calculate PnL based on last synced position."""
        if not self.last_pos:
            return 0.0
        
        qty = float(self.last_pos.get("qty") or self.last_pos.get("positionAmount") or 0)
        entry = float(self.last_pos.get("entryPrice") or self.last_pos.get("avgPrice") or 0)
        side = self.last_pos.get("side") or ("LONG" if qty > 0 else "SHORT")
        
        if side == "LONG":
            return (current_price - entry) * abs(qty)
        else:
            return (entry - current_price) * abs(qty)
