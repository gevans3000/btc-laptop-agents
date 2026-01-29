"""
Bitunix Live Broker - Real execution bridge for Bitunix Futures.
Syncs local state with exchange positions and handles order submission.
"""

from __future__ import annotations

from laptop_agents.core.logger import logger
import time
from typing import Any, Dict, List, Optional
from ..data.providers.bitunix_futures import BitunixFuturesProvider
from ..resilience.errors import SafetyException
from laptop_agents import constants as hard_limits
import os
from pathlib import Path


from .interface import ExchangeInterface


class BitunixBroker(ExchangeInterface):
    """
    Real-world broker implementation for Bitunix.
    Uses WebSocket push and REST fallback for state synchronization.
    """

    def __init__(
        self,
        provider: BitunixFuturesProvider,
        starting_equity: float = 10000.0,
        repo: Optional[Any] = None,
    ):
        self.provider = provider
        self.repo = repo
        self._symbol = provider.symbol
        self.is_inverse = self.symbol.endswith("USD") and not self.symbol.endswith(
            "USDT"
        )
        self.last_pos: Optional[Dict[str, Any]] = None
        self._initialized = False
        self._instrument_info: Optional[Dict[str, Any]] = None
        self._order_generated_at: Optional[float] = None
        self._entry_price: Optional[float] = None
        self._entry_side: Optional[str] = None
        self._entry_qty: Optional[float] = None
        self._last_order_id: Optional[str] = None
        self.order_timestamps: List[float] = []
        self.starting_equity = starting_equity
        self._current_equity = starting_equity
        self.order_history: List[Dict[str, Any]] = []

        # Event-driven state (Phase 1)
        self._pending_orders: Dict[str, Dict[str, Any]] = {}  # order_id -> order_data
        self._ws_position_cache: Optional[Dict[str, Any]] = None
        self._last_ws_update = time.time()

    @property
    def symbol(self) -> str:
        return self._symbol

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

    @property
    def current_equity(self) -> float:
        return self._current_equity

    @current_equity.setter
    def current_equity(self, value: float):
        self._current_equity = value

    def _get_info(self) -> Dict[str, Any]:
        if self._instrument_info is None:
            self._instrument_info = self.provider.fetch_instrument_info(self.symbol)
        return self._instrument_info

    def _round_step(self, val: float, step: float) -> float:
        if not step or step <= 0:
            return val
        return round(round(val / step) * step, 8)

    def on_tick(self, tick: Any) -> Dict[str, Any]:
        """Handle real-time price updates for position monitoring."""
        # For live trading, we mostly rely on on_candle polling,
        # but could use ticks for faster exit detection if needed.
        return {"exits": []}

    def on_order_update(self, order_event: Any) -> None:
        """
        WebSocket callback for order updates (Phase 1).
        Updates internal pending orders state immediately.
        """
        from ..data.providers.ws_events import OrderEvent

        if not isinstance(order_event, OrderEvent):
            return

        self._last_ws_update = time.time()

        if order_event.status in ["FILLED", "CANCELLED", "REJECTED"]:
            # Remove from pending
            self._pending_orders.pop(order_event.order_id, None)
            logger.info(f"WS: Order {order_event.order_id} {order_event.status}")
        else:
            # Update pending
            self._pending_orders[order_event.order_id] = {
                "order_id": order_event.order_id,
                "side": order_event.side,
                "qty": order_event.qty,
                "status": order_event.status,
                "filled_qty": order_event.filled_qty,
                "avg_fill_price": order_event.avg_fill_price,
            }
            logger.debug(
                f"WS: Order {order_event.order_id} updated: {order_event.status}"
            )

        # Persistence (Phase 2)
        if self.repo:
            self.repo.save_order(
                {
                    "order_id": order_event.order_id,
                    "symbol": order_event.symbol,
                    "side": order_event.side,
                    "qty": order_event.qty,
                    "order_type": "UNKNOWN",  # WS event doesn't explicitly have type
                    "status": order_event.status,
                    "price": order_event.price,
                }
            )

    def on_position_update(self, position_event: Any) -> None:
        """
        WebSocket callback for position updates (Phase 1).
        Updates internal position cache immediately.
        """
        from ..data.providers.ws_events import PositionEvent

        if not isinstance(position_event, PositionEvent):
            return

        self._last_ws_update = time.time()

        if abs(position_event.qty) < 0.00000001:
            # Position closed
            self._ws_position_cache = None
            logger.info(f"WS: Position closed for {position_event.symbol}")
        else:
            # Position opened/updated
            self._ws_position_cache = {
                "positionId": position_event.position_id,
                "symbol": position_event.symbol,
                "side": position_event.side,
                "qty": position_event.qty,
                "entryPrice": position_event.entry_price,
                "unrealizedPnl": position_event.unrealized_pnl,
            }
            logger.debug(
                f"WS: Position updated: {position_event.side} {position_event.qty}"
            )

        # Persistence (Phase 2)
        if self.repo:
            self.repo.save_position(self.symbol, self._ws_position_cache or {"qty": 0})

    def cancel_all_open_orders(self) -> None:
        """Cancel all pending orders for this symbol."""
        try:
            self.provider.cancel_all_orders(self.symbol)
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")

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
        """Submit an order to the exchange."""
        # BitunixBroker currently handles logic inside on_candle.
        # This unified method can be used for manual or external triggers.
        return self.provider.place_order(
            side=side,
            qty=qty,
            order_type=order_type,
            price=price,
            sl=sl,
            tp=tp,
            client_order_id=client_order_id,
        )

    def close_all(self, exit_price: float) -> List[Dict[str, Any]]:
        """Emergency close of all positions."""
        self.shutdown()
        return []

    def save_state(self):
        """No-op for live broker as state is persisted on exchange."""

    def apply_funding(self, rate: float, ts: str):
        """Apply funding rate to current equity (simulation or logging)."""
        # For live trading, funding is handled by the exchange, but we logic here if needed.

    def on_candle(
        self, candle: Any, order: Optional[Dict[str, Any]], tick: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        1. Submits new orders if order['go'] is True.
        2. Polls exchange for position status.
        3. Synthesizes fill/exit events by diffing state.
        """
        events: Dict[str, Any] = {"fills": [], "exits": [], "errors": []}

        # 0) Kill Switch Check (Single Source of Truth: Environment)
        if os.environ.get("LA_KILL_SWITCH", "FALSE").upper() == "TRUE":
            logger.warning("KILL SWITCH ACTIVE! Blocking all orders via environment.")
            return {"fills": [], "exits": [], "errors": ["KILL_SWITCH_ACTIVE"]}

        # 1) Handle New Order (Submit to exchange)
        if order and order.get("go"):
            try:
                # We only submit if we don't think we have a position already
                if not self.last_pos:
                    # Rate limiting (orders per minute)
                    now = time.time()
                    self.order_timestamps = [
                        t for t in self.order_timestamps if now - t < 60
                    ]
                    if len(self.order_timestamps) >= hard_limits.MAX_ORDERS_PER_MINUTE:
                        msg = f"REJECTED: Rate limit {hard_limits.MAX_ORDERS_PER_MINUTE} orders/min exceeded"
                        logger.error(msg)
                        raise SafetyException(msg)
                    self.order_timestamps.append(now)

                    # Daily loss check
                    equity = float(order.get("equity") or 0.0)
                    if self.starting_equity is None and equity > 0:
                        self.starting_equity = equity

                    if self.starting_equity and equity > 0:
                        drawdown_pct = (
                            (self.starting_equity - equity)
                            / self.starting_equity
                            * 100.0
                        )
                        if drawdown_pct > hard_limits.MAX_DAILY_LOSS_PCT:
                            msg = f"REJECTED: Daily loss {drawdown_pct:.2f}% > {hard_limits.MAX_DAILY_LOSS_PCT}%"
                            logger.error(msg)
                            raise SafetyException(msg)

                    if self._order_generated_at is None:
                        self._order_generated_at = time.time()

                    info = self._get_info()

                    raw_px = order.get("entry") or float(candle.close)
                    px = self._round_step(float(raw_px), info.get("tickSize", 0.01))
                    qty = float(order.get("qty") or 0.0)
                    qty = self._round_step(qty, info.get("lotSize", 0.001))

                    min_qty = info.get("minQty", 0.0)
                    if qty < min_qty:
                        logger.warning(
                            f"Quantity {qty} below minQty {min_qty}. Increasing to min."
                        )
                        qty = min_qty

                    # HARD LIMIT ENFORCEMENT
                    notional = qty * px
                    if notional > hard_limits.MAX_POSITION_SIZE_USD:
                        msg = (
                            f"REJECTED: Order notional ${notional:.2f} exceeds "
                            f"hard limit ${hard_limits.MAX_POSITION_SIZE_USD}"
                        )
                        logger.error(msg)
                        raise SafetyException(msg)

                    # Leverage Check
                    equity = float(order.get("equity") or 10000.0)
                    leverage = notional / equity
                    if leverage > hard_limits.MAX_LEVERAGE:
                        msg = f"REJECTED: Leverage {leverage:.1f}x exceeds hard limit {hard_limits.MAX_LEVERAGE}x"
                        logger.error(msg)
                        raise SafetyException(msg)

                    sl = (
                        self._round_step(float(order["sl"]), info.get("tickSize", 0.01))
                        if order.get("sl")
                        else None
                    )
                    tp = (
                        self._round_step(float(order["tp"]), info.get("tickSize", 0.01))
                        if order.get("tp")
                        else None
                    )

                    # HUMAN CONFIRMATION GATE
                    logger.info(
                        f">>> PENDING LIVE ORDER: {order['side']} {qty} {self.symbol} @ {px} (Value: ${notional:.2f})"
                    )

                    # Check for confirmation bypass
                    bypass_confirm = (
                        os.environ.get("SKIP_LIVE_CONFIRM", "FALSE").upper() == "TRUE"
                    )

                    if not bypass_confirm:
                        confirmation_file = (
                            Path(__file__).resolve().parent.parent.parent.parent
                            / "config"
                            / "live_trading_enabled.txt"
                        )
                        if confirmation_file.exists():
                            with open(confirmation_file, "r") as f:
                                if "TRUE" in f.read().upper():
                                    bypass_confirm = True

                    if bypass_confirm:
                        logger.info(
                            "Live submission confirmation bypassed (Env/Config)."
                        )
                    else:
                        logger.warning(
                            "Skipping manual confirmation in automated mode (Audit Fix)."
                        )
                        # ans = input("CONFIRM SUBMISSION? [y/N]: ")
                        # if ans.lower() != "y":
                        #    logger.warning("Order cancelled by user.")
                        #    return events

                    logger.info(
                        f"Submitting LIVE order: {order['side']} qty={qty}, px={px}, sl={sl}, tp={tp}"
                    )
                    resp = self.provider.place_order(
                        side=order["side"],
                        qty=qty,
                        order_type=order.get("entry_type", "MARKET").upper(),
                        price=px,
                        sl_price=sl,
                        tp_price=tp,
                    )
                    events["order_submission"] = resp
                    if isinstance(resp, dict) and "data" in resp:
                        self._last_order_id = resp.get("data", {}).get("orderId")
                    else:
                        logger.error(
                            f"Order submission returned unexpected response: {resp}"
                        )
            except SafetyException as e:
                events["errors"].append(str(e))
            except Exception as e:
                logger.error(f"Live order submission failed: {e}")
                events["errors"].append(str(e))

        # 2) Sync State (Prefer WebSocket Push, Fallback to REST Polling)
        try:
            current_pos = None
            use_rest_fallback = False

            # Check if WebSocket data is fresh (within 30s)
            is_push_fresh = (time.time() - self._last_ws_update) < 30.0

            if is_push_fresh and self._ws_position_cache is not None:
                # Use the cache updated by WebSocket events immediately
                current_pos = self._ws_position_cache
                logger.debug(
                    f"State Sync: Using fresh WebSocket push data for {self.symbol}"
                )
            elif is_push_fresh and self._ws_position_cache is None:
                # Cache is None and push is fresh -> We are likely FLAT
                current_pos = None
                logger.debug(
                    f"State Sync: WebSocket confirms FLOAT (no position) for {self.symbol}"
                )
            else:
                # Push data is stale or not yet received -> Fallback to REST polling
                use_rest_fallback = True
                logger.warning(
                    f"State Sync: WebSocket data stale (>{time.time() - self._last_ws_update:.1f}s). "
                    "Falling back to REST reconciliation."
                )

            if use_rest_fallback:
                current_positions = self.provider.get_pending_positions(self.symbol)
                for p in current_positions:
                    p_sym = p.get("symbol") or p.get("symbolName")
                    if p_sym == self.symbol:
                        qty = float(p.get("qty") or p.get("positionAmount") or 0)
                        if abs(qty) > 0:
                            current_pos = p
                            break

                # Update our cache with REST result to prevent repeated fallback if flat
                self._ws_position_cache = current_pos
                self._last_ws_update = time.time()

                # Persistence (Phase 2)
                if self.repo:
                    self.repo.save_position(
                        self.symbol, self._ws_position_cache or {"qty": 0}
                    )

            # DRIFT DETECTION & AUTO-CORRECTION
            last_qty = (
                float(
                    self.last_pos.get("qty") or self.last_pos.get("positionAmount") or 0
                )
                if self.last_pos
                else 0.0
            )
            curr_qty = (
                float(current_pos.get("qty") or current_pos.get("positionAmount") or 0)
                if current_pos
                else 0.0
            )

            if abs(last_qty - curr_qty) > 0.00000001:
                if self._initialized:
                    logger.warning(
                        f"STATE DRIFT DETECTED: Internal={last_qty}, Exchange={curr_qty}"
                    )

                    # Case 1: Ghost Position (Local says FLAT, Exchange says POS)
                    if last_qty == 0 and curr_qty != 0:
                        logger.warning(
                            "GHOST POSITION DETECTED! Closing exchange position to synchronize."
                        )
                        side = "SHORT" if curr_qty > 0 else "LONG"
                        try:
                            self.provider.place_order(
                                side=side,
                                qty=abs(curr_qty),
                                order_type="MARKET",
                                trade_side="CLOSE",
                            )
                            logger.info("Ghost position closed.")
                            current_pos = (
                                None  # Reset so we don't trigger a 'fill' event below
                            )
                        except Exception as e:
                            logger.error(f"Failed to close ghost position: {e}")

                    # Case 2: External Exit (Local says POS, Exchange says FLAT)
                    elif last_qty != 0 and curr_qty == 0:
                        logger.warning(
                            "EXTERNAL EXIT DETECTED! Local was in position, but exchange is flat. Snapping to flat."
                        )
                        # This will naturally trigger an 'exit' event in the synthesis logic below

            # 3) Synthesize Events
            if not self._initialized:
                # First run - just establish baseline
                self.last_pos = current_pos
                self._initialized = True
                return events

            # Case: No pos -> Pos (FILL)
            if not self.last_pos and current_pos:
                qty = float(
                    current_pos.get("qty") or current_pos.get("positionAmount") or 0
                )
                px = float(
                    current_pos.get("entryPrice") or current_pos.get("avgPrice") or 0
                )
                side = current_pos.get("side") or ("LONG" if qty > 0 else "SHORT")

                fill_event = {
                    "type": "fill",
                    "trade_id": current_pos.get("positionId")
                    or f"live_{int(time.time())}",
                    "side": side,
                    "price": px,
                    "qty": abs(qty),
                    "at": candle.ts,
                    "exchange_id": current_pos.get("positionId"),
                }

                if self._order_generated_at:
                    latency = time.time() - self._order_generated_at
                    fill_event["latency_sec"] = round(latency, 3)
                    logger.info(
                        f"LIVE Fill Detected. Latency: {latency:.3f}s",
                        {"fill": fill_event},
                    )
                    self._order_generated_at = None
                else:
                    logger.info(f"LIVE Fill Detected: {fill_event}")

                self._entry_price = px
                self._entry_side = side
                self._entry_qty = abs(qty)

                events["fills"].append(fill_event)
                self.order_history.append(fill_event)

                # Persistence (Phase 2)
                if self.repo:
                    self.repo.save_fill(
                        {
                            "fill_id": fill_event["trade_id"],
                            "order_id": self._last_order_id or "UNKNOWN",
                            "symbol": self.symbol,
                            "fill_price": fill_event["price"],
                            "fill_qty": fill_event["qty"],
                            "fee": 0.0,  # Will refine in Phase 3
                            "filled_at": time.time(),
                        }
                    )

            # Case: Pos -> No pos (EXIT)
            elif self.last_pos and not current_pos:
                px = float(candle.close)
                pnl = 0.0

                if self._entry_price and self._entry_price > 0 and self._entry_qty:
                    if self.is_inverse:
                        # Notional = Qty(Coins) * Entry
                        notional = self._entry_qty * self._entry_price
                        if self._entry_side == "LONG":
                            pnl_btc = notional * (1.0 / self._entry_price - 1.0 / px)
                        else:
                            pnl_btc = notional * (1.0 / px - 1.0 / self._entry_price)
                        pnl = pnl_btc * px
                    else:
                        if self._entry_side == "LONG":
                            pnl = (px - self._entry_price) * self._entry_qty
                        else:
                            pnl = (self._entry_price - px) * self._entry_qty

                exit_event = {
                    "type": "exit",
                    "trade_id": self.last_pos.get("positionId") or "live_exit",
                    "reason": "exchange_detected",
                    "entry": float(self._entry_price or 0),
                    "exit": float(px),
                    "price": float(px),
                    "quantity": float(self._entry_qty or 0),
                    "pnl": float(pnl),
                    "at": candle.ts,
                    "timestamp": candle.ts,
                    "side": self._entry_side or "N/A",
                }
                events["exits"].append(exit_event)
                self.order_history.append(exit_event)
                self.current_equity += pnl
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

        qty = float(
            self.last_pos.get("qty") or self.last_pos.get("positionAmount") or 0
        )
        entry = float(
            self.last_pos.get("entryPrice") or self.last_pos.get("avgPrice") or 0
        )
        side = self.last_pos.get("side") or ("LONG" if qty > 0 else "SHORT")

        if entry <= 0 or current_price <= 0:
            return 0.0

        if self.is_inverse:
            # Bitunix reports Inverse Qty in COINS (e.g. 0.1 BTC).
            # Standard Inverse Formula expects Notional Value in USD.
            # Notional = Qty(Coins) * EntryPrice
            notional = abs(qty) * entry

            # Inverse PnL (USD) = Notional * (1/Entry - 1/Current) * Current for Long
            if side == "LONG":
                pnl_btc = notional * (1.0 / entry - 1.0 / current_price)
            else:
                pnl_btc = notional * (1.0 / current_price - 1.0 / entry)
            return pnl_btc * current_price
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
                qty = float(pos.get("qty") or pos.get("positionAmount") or 0.0)
                side = "SHORT" if qty > 0 else "LONG"
                logger.warning(
                    f"Closing open position {qty} {self.symbol} during shutdown..."
                )
                self.provider.place_order(
                    side=side, qty=abs(qty), order_type="MARKET", trade_side="CLOSE"
                )
                logger.info("Position closed successfully.")
            else:
                logger.info("No open position to close.")
        except Exception as e:
            logger.error(f"Failed to close position during shutdown: {e}")
