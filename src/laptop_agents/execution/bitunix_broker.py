"""
Bitunix Live Broker - Real execution bridge for Bitunix Futures.
Syncs local state with exchange positions and handles order submission.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from ..data.providers.bitunix_futures import BitunixFuturesProvider

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

    def on_candle(self, candle: Any, order: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        1. Submits new orders if order['go'] is True.
        2. Polls exchange for position status.
        3. Synthesizes fill/exit events by diffing state.
        """
        events: Dict[str, Any] = {"fills": [], "exits": [], "errors": []}

        # 1) Handle New Order (Submit to exchange)
        if order and order.get("go"):
            try:
                # We only submit if we don't think we have a position already 
                # (Safety check handled by Supervisor usually, but extra check here)
                if not self.last_pos:
                    logger.info(f"Submitting LIVE order: {order}")
                    resp = self.provider.place_order(
                        side=order["side"],
                        qty=order["qty"],
                        order_type=order.get("entry_type", "MARKET").upper(),
                        price=order.get("entry"),
                        sl_price=order.get("sl"),
                        tp_price=order.get("tp")
                    )
                    events["order_submission"] = resp
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
