"""
Bitunix Live Broker - Real execution bridge for Bitunix Futures.
Syncs local state with exchange positions and handles order submission.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from ..data.providers.bitunix_futures import BitunixFuturesProvider
from ..resilience.errors import SafetyException
from ..core import hard_limits
import os
from pathlib import Path

logger = logging.getLogger(__name__)

class BitunixBroker:
    """
    Real-world broker implementation for Bitunix.
    Polls position state to synthesize fill/exit events.
    """

    def __init__(self, provider: BitunixFuturesProvider):
        self.provider = provider
        self.symbol = provider.symbol
        self.is_inverse = self.symbol == "BTCUSD"
        self.last_pos: Optional[Dict[str, Any]] = None
        self._initialized = False
        self._instrument_info: Optional[Dict[str, Any]] = None
        self._order_generated_at: Optional[float] = None
        self._entry_price: Optional[float] = None
        self._entry_side: Optional[str] = None
        self._entry_qty: Optional[float] = None
        self._last_order_id: Optional[str] = None

    @property
    def pos(self) -> Optional[Any]:
        if not self.last_pos:
            return None
        
        # Simple object with .side to satisfy timed_session.py
        class SimplePos:
            def __init__(self, d):
                qty = float(d.get("qty") or d.get("positionAmount") or 0)
                self.side = d.get("side") or ("LONG" if qty > 0 else "SHORT")
        
        return SimplePos(self.last_pos)

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
                    if self._order_generated_at is None:
                         self._order_generated_at = time.time()
                    
                    info = self._get_info()
                    
                    raw_px = order.get("entry") or float(candle.close)
                    px = self._round_step(float(raw_px), info["tickSize"])
                    
                    # DYNAMIC SIZING: Derived from order object
                    qty = float(order.get("qty") or 0.0)
                    qty = self._round_step(qty, info["lotSize"])
                    
                    # Pre-flight safety check
                    if qty < info["minQty"]:
                        logger.warning(f"Quantity {qty} below minQty {info['minQty']}. Increasing to min.")
                        qty = info["minQty"]
                    
                    # HARD LIMIT ENFORCEMENT
                    notional = qty * px
                    if notional > hard_limits.MAX_POSITION_SIZE_USD:
                        msg = f"REJECTED: Order notional ${notional:.2f} exceeds hard limit ${hard_limits.MAX_POSITION_SIZE_USD}"
                        logger.error(msg)
                        raise SafetyException(msg)
                    
                    # Leverage Check
                    equity = float(order.get("equity") or 10000.0)
                    leverage = notional / equity
                    if leverage > hard_limits.MAX_LEVERAGE:
                        msg = f"REJECTED: Leverage {leverage:.1f}x exceeds hard limit {hard_limits.MAX_LEVERAGE}x"
                        logger.error(msg)
                        raise SafetyException(msg)
                    
                    sl = self._round_step(float(order["sl"]), info["tickSize"]) if order.get("sl") else None
                    tp = self._round_step(float(order["tp"]), info["tickSize"]) if order.get("tp") else None

                    # HUMAN CONFIRMATION GATE
                    logger.info(f">>> PENDING LIVE ORDER: {order['side']} {qty} {self.symbol} @ {px} (Value: ${notional:.2f})")

                    # Check for confirmation bypass
                    bypass_confirm = os.environ.get("SKIP_LIVE_CONFIRM", "FALSE").upper() == "TRUE"
                    
                    if not bypass_confirm:
                        confirmation_file = Path(__file__).resolve().parent.parent.parent.parent / "config" / "live_trading_enabled.txt"
                        if confirmation_file.exists():
                            with open(confirmation_file, "r") as f:
                                if "TRUE" in f.read().upper():
                                    bypass_confirm = True
                    
                    if bypass_confirm:
                        logger.info("Live submission confirmation bypassed (Env/Config).")
                    else:
                        ans = input(f"CONFIRM SUBMISSION? [y/N]: ")
                        if ans.lower() != 'y':
                            logger.warning("Order cancelled by user.")
                            return events
                    
                    logger.info(f"Submitting LIVE order: {order['side']} qty={qty}, px={px}, sl={sl}, tp={tp}")
                    resp = self.provider.place_order(
                        side=order["side"],
                        qty=qty,
                        order_type=order.get("entry_type", "MARKET").upper(),
                        price=px,
                        sl_price=sl,
                        tp_price=tp
                    )
                    events["order_submission"] = resp
                    if isinstance(resp, dict) and "data" in resp:
                         self._last_order_id = resp.get("data", {}).get("orderId")
                    else:
                         logger.error(f"Order submission returned unexpected response: {resp}")
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
            
            # DRIFT DETECTION & AUTO-CORRECTION
            last_qty = float(self.last_pos.get("qty") or self.last_pos.get("positionAmount") or 0) if self.last_pos else 0.0
            curr_qty = float(current_pos.get("qty") or current_pos.get("positionAmount") or 0) if current_pos else 0.0
            
            if abs(last_qty - curr_qty) > 0.00000001:
                if self._initialized:
                    logger.warning(f"STATE DRIFT DETECTED: Internal={last_qty}, Exchange={curr_qty}")
                    
                    # Case 1: Ghost Position (Local says FLAT, Exchange says POS)
                    if last_qty == 0 and curr_qty != 0:
                        logger.warning("GHOST POSITION DETECTED! Closing exchange position to synchronize.")
                        side = "SHORT" if curr_qty > 0 else "LONG"
                        try:
                            self.provider.place_order(
                                side=side,
                                qty=abs(curr_qty),
                                order_type="MARKET",
                                trade_side="CLOSE"
                            )
                            logger.info("Ghost position closed.")
                            current_pos = None # Reset so we don't trigger a 'fill' event below
                        except Exception as e:
                            logger.error(f"Failed to close ghost position: {e}")

                    # Case 2: External Exit (Local says POS, Exchange says FLAT)
                    elif last_qty != 0 and curr_qty == 0:
                        logger.warning("EXTERNAL EXIT DETECTED! Local was in position, but exchange is flat. Snapping to flat.")
                        # This will naturally trigger an 'exit' event in the synthesis logic below
            
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
                
                if self._order_generated_at:
                    latency = time.time() - self._order_generated_at
                    fill_event["latency_sec"] = round(latency, 3)
                    logger.info(f"LIVE Fill Detected. Latency: {latency:.3f}s", {"fill": fill_event})
                    self._order_generated_at = None
                else:
                    logger.info(f"LIVE Fill Detected: {fill_event}")
                
                self._entry_price = px
                self._entry_side = side
                self._entry_qty = abs(qty)
                
                events["fills"].append(fill_event)

            # Case: Pos -> No pos (EXIT)
            elif self.last_pos and not current_pos:
                px = float(candle.close)
                pnl = 0.0

                if self._entry_price and self._entry_price > 0:
                    if self.is_inverse:
                        # Notional = Qty(Coins) * Entry
                        notional = self._entry_qty * self._entry_price
                        if self._entry_side == "LONG":
                            pnl = notional * (1.0/self._entry_price - 1.0/px)
                        else:
                            pnl = notional * (1.0/px - 1.0/self._entry_price)
                    else:
                        if self._entry_side == "LONG":
                            pnl = (px - self._entry_price) * self._entry_qty
                        else:
                            pnl = (self._entry_price - px) * self._entry_qty

                exit_event = {
                    "type": "exit",
                    "reason": "exchange_detected",
                    "price": px,
                    "pnl": pnl,
                    "at": candle.ts
                }
                events["exits"].append(exit_event)
                logger.info(f"LIVE Exit Detected: {exit_event}")

                # Reset entry tracking
                self._entry_price = None
                self._entry_side = None
                self._entry_qty = None

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
        
        
        if entry <= 0 or current_price <= 0:
            return 0.0
            
        if self.is_inverse:
             # Bitunix reports Inverse Qty in COINS (e.g. 0.1 BTC).
             # Standard Inverse Formula expects Notional Value in USD.
             # Notional = Qty(Coins) * EntryPrice
             notional = abs(qty) * entry
             
             # Inverse PnL (BTC) = Notional * (1/Entry - 1/Current) for Long
             if side == "LONG":
                 return notional * (1.0/entry - 1.0/current_price)
             else:
                 return notional * (1.0/current_price - 1.0/entry)
        else:
            if side == "LONG":
                return (current_price - entry) * abs(qty)
            else:
                return (entry - current_price) * abs(qty)

    def shutdown(self):
        """
        Emergency Kill Switch: 
        1. Cancel all open orders for this symbol.
        2. Close any open positions for this symbol.
        """
        logger.warning(f"SHUTDOWN CALLED for {self.symbol}. Cleaning up...")
        
        # 1. Cancel all orders
        try:
            resp = self.provider.cancel_all_orders(self.symbol)
            logger.info(f"Cancel all orders response: {resp}")
        except Exception as e:
            logger.error(f"Failed to cancel all orders during shutdown: {e}")
            
        # 2. Close position if exists
        try:
            positions = self.provider.get_pending_positions(self.symbol)
            pos = None
            for p in positions:
                p_sym = p.get("symbol") or p.get("symbolName")
                if p_sym == self.symbol:
                    qty = float(p.get("qty") or p.get("positionAmount") or 0)
                    if abs(qty) > 0:
                        pos = p
                        break
            
            if pos:
                qty = float(pos.get("qty") or pos.get("positionAmount"))
                side = "SHORT" if qty > 0 else "LONG"
                logger.warning(f"Closing open position {qty} {self.symbol} during shutdown...")
                self.provider.place_order(
                    side=side,
                    qty=abs(qty),
                    order_type="MARKET",
                    trade_side="CLOSE"
                )
                logger.info("Position closed successfully.")
            else:
                logger.info("No open position to close.")
        except Exception as e:
            logger.error(f"Failed to close position during shutdown: {e}")
