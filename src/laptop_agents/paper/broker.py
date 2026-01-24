from __future__ import annotations

from typing import Any, Dict, List, Optional
from ..trading.helpers import apply_slippage
from laptop_agents.core.events import append_event
from laptop_agents.core.logger import logger
import time
import random
import uuid
from pathlib import Path
from datetime import datetime, timezone
from cachetools import TTLCache
from collections import deque
from .broker_types import Position
from .broker_risk import validate_risk_limits
from .broker_state import BrokerStateMixin
from ..storage.position_store import PositionStore


class PaperBroker(BrokerStateMixin):
    """Very simple broker:
    - one position max
    - one TP + one SL
    - conservative intrabar resolution (stop-first if both touched)
    """

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        fees_bps: float = 0.0,
        slip_bps: float = 0.0,
        starting_equity: float = 10000.0,
        state_path: Optional[str] = None,
        random_seed: Optional[int] = None,
        strategy_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.symbol = symbol
        self.strategy_config = strategy_config or {}
        self.rng = random.Random(random_seed)
        self.last_trade_time: float = 0.0
        self.min_trade_interval_sec: float = 60.0  # 1 minute minimum between trades
        self.pos = None  # type: ignore  # type: ignore
        self.is_inverse = self.symbol.endswith("USD") and not self.symbol.endswith(
            "USDT"
        )
        self.fees_bps = fees_bps
        self.slip_bps = slip_bps
        self.starting_equity = starting_equity
        self.current_equity = starting_equity
        self.exchange_fees: Dict[str, float] = {"maker": -0.0002, "taker": 0.0005}
        self._load_exchange_config()
        # Override with constructor args if provided to support old tests
        if fees_bps != 0:
            self.exchange_fees = {
                "maker": fees_bps / 10000.0,
                "taker": fees_bps / 10000.0,
            }
        self.processed_order_ids: set[str] = set()
        self._idempotency_cache: TTLCache[str, Any] = TTLCache(maxsize=1000, ttl=5)
        self.order_timestamps: List[float] = []
        self.order_history: List[Dict[str, Any]] = []

        self.store: Optional[PositionStore] = None
        self.state_path: Optional[str] = None
        if state_path:
            # Enforce .db extension for SQLite store
            db_path = Path(state_path).with_suffix(".db")
            self.state_path = str(db_path)
            self.store = PositionStore(self.state_path)
        else:
            self.state_path = None

        self.working_orders: List[Dict[str, Any]] = []
        self.max_position_per_symbol: Dict[str, float] = {}
        self._load_risk_config()
        if self.store:
            self._load_state()

    def on_candle(
        self, candle: Any, order: Optional[Dict[str, Any]], tick: Optional[Any] = None
    ) -> Dict[str, Any]:
        events: Dict[str, Any] = {"fills": [], "exits": []}

        # 0) process working orders
        working_fills = self._process_working_orders(candle)
        events["fills"].extend(working_fills)

        # 1) manage open position
        if self.pos is not None:
            self.pos.bars_open += 1
            max_bars = self.strategy_config.get(
                "max_bars_open", 50
            )  # Phase 2: Force exit after 50 bars
            exit_event: Optional[Dict[str, Any]] = None
            if self.pos.bars_open > max_bars:
                logger.warning(
                    f"STALE_EXIT: Position open for {self.pos.bars_open} > {max_bars} bars. Force closing."
                )
                close_px = float(candle.close)
                exit_event = self._exit(candle.ts, close_px, "STALE_EXIT")
            else:
                exit_event = self._check_exit(candle)

            if exit_event:
                events["exits"].append(exit_event)
                self.pos = None  # type: ignore

        # 2) open new position if none
        if self.pos is None and order and order.get("go"):
            fill = self._try_fill(candle, order, tick=tick)
            if fill:
                events["fills"].append(fill)
                if self.state_path:
                    self._save_state()

        return events

    def on_tick(self, tick: Any) -> Dict[str, Any]:
        """Process a real-time tick for SL/TP monitoring."""
        events: Dict[str, Any] = {"exits": []}
        if self.pos is not None:
            exit_event = self._check_tick_exit(tick)
            if exit_event:
                events["exits"].append(exit_event)
                self.pos = None  # type: ignore
                if self.state_path:
                    self._save_state()
        return events

    def _validate_risk_limits(
        self,
        order: Dict[str, Any],
        candle: Any,
        equity: float,
        is_working: bool,
    ) -> bool:
        return validate_risk_limits(self, order, candle, equity, is_working)

    def _close_position_fifo(
        self,
        side: str,
        actual_qty: float,
        fill_px_slipped: float,
        entry_fees: float,
        candle: Any,
    ) -> Dict[str, Any]:
        """Execute FIFO closing logic for position reduction/exit."""
        assert self.pos is not None
        # Plan 4.1: FIFO Closing Logic
        remaining_qty = actual_qty
        total_realized_pnl = 0.0
        total_exit_fees = 0.0
        total_reduction = 0.0

        exit_fee_rate = self.exchange_fees["taker"]

        while remaining_qty > 0 and self.pos and self.pos.lots:
            lot = self.pos.lots[0]
            signed_lot_qty = lot["qty"]

            # How much of this lot can we close?
            close_qty = min(remaining_qty, signed_lot_qty)

            # Settle this portion
            avg_entry = lot["price"]
            # Pro-rate entry fees for this lot portion
            entry_fees_portion = lot["fees"] * (close_qty / signed_lot_qty)

            if self.is_inverse:
                pnl_coins = (1.0 / avg_entry - 1.0 / fill_px_slipped) * close_qty
                if side == "LONG":
                    pnl_coins = -pnl_coins  # closing short
                pnl = pnl_coins * fill_px_slipped
            else:
                pnl = (
                    (fill_px_slipped - avg_entry) * close_qty
                    if self.pos.side == "LONG"
                    else (avg_entry - fill_px_slipped) * close_qty
                )

            # Exit fees
            exit_fees = (
                abs(close_qty * fill_px_slipped if not self.is_inverse else close_qty)
                * exit_fee_rate
            )

            total_realized_pnl += pnl - exit_fees - entry_fees_portion
            total_exit_fees += exit_fees + entry_fees_portion
            total_reduction += close_qty

            if close_qty < lot["qty"]:
                lot["qty"] -= close_qty
                lot["fees"] -= entry_fees_portion
                remaining_qty = 0
            else:
                self.pos.lots.popleft()
                remaining_qty -= close_qty

        self.pos.qty -= total_reduction
        self.current_equity += total_realized_pnl

        close_event = {
            "type": "exit" if self.pos.qty <= 0.00000001 else "partial_exit",
            "trade_id": self.pos.trade_id,
            "side": side,
            "price": float(fill_px_slipped),
            "qty": float(total_reduction),
            "pnl": float(total_realized_pnl),
            "fees": float(total_exit_fees),
            "at": candle.ts,
        }
        self.order_history.append(close_event)
        if self.pos.qty <= 0.00000001:
            self.pos = None  # type: ignore

        if self.state_path:
            self._save_state()
        self.last_trade_time = time.time()
        return close_event

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
        """Unified entry point for internal orders."""
        side_upper = side.upper()
        normalized_side = "LONG" if side_upper in ["BUY", "LONG"] else "SHORT"
        order = {
            "side": normalized_side,
            "qty": qty,
            "entry_type": order_type.lower(),
            "entry": price or 0.0,
            "sl": sl or 0.0,
            "tp": tp or 0.0,
            "client_order_id": client_order_id or uuid.uuid4().hex,
            "go": True,
            "created_at": time.time(),
        }
        self.working_orders.append(order)
        logger.info(
            f"PAPER ORDER PLACED: {side} {qty} {order_type} (ID: {order['client_order_id']})"
        )
        return {"status": "success", "order": order}

    def _try_fill(
        self,
        candle: Any,
        order: Dict[str, Any],
        is_working: bool = False,
        tick: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        # Idempotency check
        client_order_id = order.get("client_order_id") or uuid.uuid4().hex
        if not is_working:
            if client_order_id in self._idempotency_cache:
                logger.warning(
                    f"Duplicate order {client_order_id} detected, returning cached result"
                )
                return self._idempotency_cache[client_order_id]

            if client_order_id in self.processed_order_ids:
                logger.warning(f"Duplicate order {client_order_id} ignored (long-term)")
                return None

            self.processed_order_ids.add(client_order_id)

        equity = float(order.get("equity") or self.current_equity)

        if not self._validate_risk_limits(order, candle, equity, is_working):
            return None

        entry_type = order["entry_type"]
        entry = float(order["entry"])
        side = order["side"]
        qty = float(order["qty"])
        sl = float(order["sl"])
        tp = float(order["tp"])

        if entry_type == "market":
            if tick and tick.bid and tick.ask:
                # BUY fills at ASK, SELL fills at BID
                fill_px = float(tick.ask) if side == "LONG" else float(tick.bid)
                actual_slip_bps = 0.0  # Spread essentially IS the slippage
            else:
                # 1.2 Synthesize Bid/Ask Spread in Tickless Mode (Only if slippage is enabled)
                half_spread_bps = 5.0 if self.slip_bps > 0 else 0.0
                close = float(candle.close)
                ask = close * (1 + half_spread_bps / 10000)
                bid = close * (1 - half_spread_bps / 10000)
                fill_px = ask if side == "LONG" else bid
                actual_slip_bps = 0.0  # Spread is explicitly modeled in fill_px
        else:
            # limit fill if touched
            if not (candle.low <= entry <= candle.high):
                return None
            fill_px = entry
            actual_slip_bps = 0.0

        # Plan 3.1: Realistic Slippage Model
        if entry_type == "market" and self.slip_bps > 0:
            # 30bps slippage as per plan
            fill_px = fill_px * (1 + 0.0003 * (1 if side == "LONG" else -1))
            logger.debug(f"Applied 30bps market slippage: {fill_px}")

        # Liquidity Capping
        candle_vol = getattr(candle, "volume", 0)
        max_fill_qty = candle_vol * 0.1 if candle_vol > 0 else qty
        actual_qty = min(qty, max_fill_qty)

        if actual_qty < qty:
            logger.info(
                f"PARTIAL FILL: Capped {qty:.4f} to {actual_qty:.4f} (10% of candle volume)"
            )

        # 3.2 Order Book Impact & Depth Simulation (Only if slippage is enabled)
        impact_pct = 0.0
        if self.slip_bps > 0:
            simulated_liquidity = 1000000.0  # 1M USD depth
            order_notional = actual_qty * fill_px
            impact_pct = (order_notional / simulated_liquidity) * 0.05

            if side == "LONG":
                fill_px = fill_px * (1.0 + impact_pct)
            else:
                fill_px = fill_px * (1.0 - impact_pct)

            if impact_pct > 0.00001:  # 0.1 bps
                logger.info(
                    f"Market Impact Penalty: {impact_pct * 10000.0:.2f} bps (${impact_pct * order_notional:.2f})"
                )

        # Apply slippage and fees to entry
        if tick and tick.bid and tick.ask and entry_type == "market":
            # Already used bid/ask, just add tiny randomized jitter (0-0.2 bps) for network arrival variance
            effective_slip = self.rng.uniform(0.0, 0.2)
        else:
            base_slip = actual_slip_bps
            random_slip_factor = self.rng.uniform(
                0.5, 1.5
            )  # 50% to 150% of base slippage
            effective_slip = base_slip * random_slip_factor

        fill_px_slipped = apply_slippage(
            fill_px, is_entry=True, is_long=(side == "LONG"), slip_bps=effective_slip
        )

        # Add simulated latency log
        simulated_latency_ms = self.rng.randint(50, 500)
        logger.debug(f"Simulated execution latency: {simulated_latency_ms}ms")
        notional = actual_qty * fill_px_slipped

        # Plan 3.2: Maker/Taker Fee Model
        is_maker = entry_type == "limit"
        fee_rate = (
            self.exchange_fees["maker"] if is_maker else self.exchange_fees["taker"]
        )
        entry_fees = notional * fee_rate

        # For Inverse, we store 'qty' as Notional USD, but the input 'qty' is in Coins.
        pos_qty = notional if self.is_inverse else actual_qty

        new_lot = {"qty": pos_qty, "price": fill_px_slipped, "fees": entry_fees}

        trade_id = client_order_id if not is_working else uuid.uuid4().hex[:12]

        if self.pos and side != self.pos.side:
            close_event = self._close_position_fifo(
                side, actual_qty, fill_px_slipped, entry_fees, candle
            )
            return close_event

        if self.pos:
            # Add to existing position (same side)
            self.pos.lots.append(new_lot)
            self.pos.qty += pos_qty
        else:
            # New position
            self.pos = Position(
                side=side,
                qty=pos_qty,
                sl=sl,
                tp=tp,
                opened_at=candle.ts,
                lots=deque([new_lot]),
                trade_id=trade_id,
            )
        fill_event = {
            "type": "fill",
            "trade_id": trade_id,
            "side": side,
            "price": fill_px_slipped,
            "qty": pos_qty,
            "sl": sl,
            "tp": tp,
            "at": candle.ts,
            "fees": entry_fees,
        }
        if actual_qty < qty:
            fill_event["partial"] = True
            fill_event["requested_qty"] = qty

            # Create a working order for the remainder
            remainder = {
                "client_order_id": f"{client_order_id or 'anon'}_remainder",
                "side": side,
                "entry_type": "limit",
                "entry": entry,  # Phase 2: Use original limit price to avoid double slippage taxation
                "qty": qty - actual_qty,
                "sl": sl,
                "tp": tp,
                "equity": equity,
                "created_at": time.time(),
            }
            self.working_orders.append(remainder)
            logger.info(f"WORKING ORDER CREATED: {qty - actual_qty:.4f} remaining")

        if self.state_path:
            self._save_state()

        self.last_trade_time = time.time()
        if client_order_id and not is_working:
            self._idempotency_cache[client_order_id] = fill_event
        return fill_event

    def _check_tick_exit(self, tick: Any) -> Optional[Dict[str, Any]]:
        """Sub-minute check for SL/TP against latest tick price."""
        assert self.pos is not None
        p = self.pos
        ts = str(tick.ts)

        if p.side == "LONG":
            # LONG exit (SELL) fills at BID
            px = float(tick.bid)
            if px <= p.sl:
                return self._exit(ts, p.sl, "SL_TICK")
            if px >= p.tp:
                return self._exit(ts, p.tp, "TP_TICK")
            if p.trail_active and px <= p.trail_stop:
                return self._exit(ts, p.trail_stop, "TRAIL_TICK")
        else:  # SHORT
            # SHORT exit (BUY) fills at ASK
            px = float(tick.ask)
            if px >= p.sl:
                return self._exit(ts, p.sl, "SL_TICK")
            if px <= p.tp:
                return self._exit(ts, p.tp, "TP_TICK")
            if p.trail_active and px >= p.trail_stop:
                return self._exit(ts, p.trail_stop, "TRAIL_TICK")

        return None

    def _check_exit(self, candle: Any) -> Optional[Dict[str, Any]]:
        assert self.pos is not None
        p = self.pos

        if self.pos is not None:
            if self.pos.bars_open > 50:
                logger.warning(f"STALE POSITION: Open for {self.pos.bars_open} bars")
                append_event(
                    {
                        "event": "StalePosition",
                        "bars_open": self.pos.bars_open,
                        "side": self.pos.side,
                        "entry": self.pos.entry,
                    },
                    paper=True,
                )

        # ATR Trailing Stop Logic (configurable mult)
        atr_mult = self.strategy_config.get("trailing_atr_mult", 1.5)
        if not p.trail_active:
            # Activate trail if profit > 0.5R
            if (
                p.side == "LONG"
                and float(candle.close) > p.entry + abs(p.entry - p.sl) * 0.5
            ):
                p.trail_active = True
                p.trail_stop = float(candle.close) - abs(p.entry - p.sl) * atr_mult
                append_event(
                    {
                        "event": "TrailActivated",
                        "side": p.side,
                        "entry": p.entry,
                        "trail_stop": p.trail_stop,
                        "current_price": float(candle.close),
                    },
                    paper=True,
                )
            elif (
                p.side == "SHORT"
                and float(candle.close) < p.entry - abs(p.entry - p.sl) * 0.5
            ):
                p.trail_active = True
                p.trail_stop = float(candle.close) + abs(p.entry - p.sl) * atr_mult
                append_event(
                    {
                        "event": "TrailActivated",
                        "side": p.side,
                        "entry": p.entry,
                        "trail_stop": p.trail_stop,
                        "current_price": float(candle.close),
                    },
                    paper=True,
                )
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
                # Use gap-open price if candle gaps past SL
                exit_price = (
                    min(p.sl, float(candle.open)) if float(candle.open) < p.sl else p.sl
                )
                return self._exit(candle.ts, exit_price, "SL")
            if tp_hit:
                return self._exit(candle.ts, p.tp, "TP")
        else:  # SHORT
            sl_hit = candle.high >= p.sl
            tp_hit = candle.low <= p.tp
            if sl_hit and tp_hit:
                return self._exit(candle.ts, p.sl, "SL_conservative")
            if sl_hit:
                # Use gap-open price if candle gaps past SL
                exit_price = (
                    max(p.sl, float(candle.open)) if float(candle.open) > p.sl else p.sl
                )
                return self._exit(candle.ts, exit_price, "SL")
            if tp_hit:
                return self._exit(candle.ts, p.tp, "TP")

        return None

    def _exit(self, ts: str, px: float, reason: str) -> Dict[str, Any]:
        assert self.pos is not None
        p = self.pos
        # Apply slippage and fees to exit
        # For exits, we usually don't have the exact tick at the moment of SL/TP hit
        # unless it's a tick-based exit.
        random_slip_factor = self.rng.uniform(0.5, 1.5)
        effective_slip = self.slip_bps * random_slip_factor
        px_slipped = apply_slippage(
            px, is_entry=False, is_long=(p.side == "LONG"), slip_bps=effective_slip
        )

        # Plan 3.3: FIFO Cost Basis for PnL
        # Calculate PnL by depleting lots FIFO
        total_entry_notional = 0.0
        total_entry_fees = 0.0

        # We'll just exit the whole position for now, as _exit is called when pos is cleared
        while p.lots:
            lot = p.lots.popleft()
            total_entry_notional += lot["qty"] * lot["price"]
            total_entry_fees += lot["fees"]

        avg_entry = total_entry_notional / p.qty

        if self.is_inverse:
            # Inverse PnL (BTC) = Notional * (1/Entry - 1/Exit) for Long
            if p.side == "LONG":
                pnl_coins = p.qty * (1.0 / avg_entry - 1.0 / px_slipped)
            else:
                pnl_coins = p.qty * (1.0 / px_slipped - 1.0 / avg_entry)

            pnl = pnl_coins * px_slipped
            # Risk calculation omitted for brevity but should use avg_entry
            risk = p.qty * abs(1.0 / avg_entry - 1.0 / p.sl) * px_slipped
        else:
            pnl = (
                (px_slipped - avg_entry) * p.qty
                if p.side == "LONG"
                else (avg_entry - px_slipped) * p.qty
            )
            risk = abs(avg_entry - p.sl) * p.qty

        # Exits are always Taker orders
        exit_fee_rate = self.exchange_fees["taker"]
        exit_fees = (
            abs(p.qty * px_slipped if not self.is_inverse else p.qty) * exit_fee_rate
        )
        net_pnl = pnl - exit_fees - total_entry_fees

        r_mult = (net_pnl / risk) if risk > 0 else 0.0
        self.current_equity += net_pnl
        exit_event = {
            "type": "exit",
            "trade_id": p.trade_id,
            "reason": reason,
            "entry": float(avg_entry),
            "exit": float(px_slipped),
            "price": float(px_slipped),
            "quantity": float(p.qty),
            "qty": float(p.qty),
            "pnl": float(net_pnl),
            "at": ts,
            "timestamp": ts,
            "fees": float(exit_fees + total_entry_fees),
            "r": float(r_mult),
            "side": p.side,
            "bars_open": p.bars_open,
        }
        self.order_history.append(exit_event)

        if self.state_path:
            self._save_state()

        return exit_event

    def save_state(self) -> None:
        """Public alias for state persistence."""
        self._save_state()

    def get_unrealized_pnl(self, current_price: float) -> float:
        if self.pos is None:
            return 0.0
        p = self.pos

        if self.is_inverse:
            if p.side == "LONG":
                return p.qty * (1.0 / p.entry - 1.0 / current_price)
            else:
                return p.qty * (1.0 / current_price - 1.0 / p.entry)
        else:
            if p.side == "LONG":
                return (current_price - p.entry) * p.qty
            else:
                return (p.entry - current_price) * p.qty

    def cancel_all_open_orders(self) -> None:
        """Alias for Plan 4.1 readiness."""
        self.shutdown()

    def close_all(self, current_price: float) -> List[Dict[str, Any]]:
        """Force close any open positions."""
        if self.pos is None:
            return []
        logger.info(f"FORCED CLOSE OF {self.pos.side} @ {current_price}")
        exit_event = self._exit(
            datetime.now(timezone.utc).isoformat(), current_price, "FORCE_CLOSE"
        )
        self.pos = None  # type: ignore
        return [exit_event]

    def apply_funding(self, rate: float, ts: str) -> None:
        """Simulate funding fee: cost = current_position_size * rate."""
        if self.pos is None:
            return

        p = self.pos
        # Note: p.qty is already in USD notional for Inverse or Coins for Linear (converted in _try_fill)
        # Actually in _try_fill: pos_qty = notional if self.is_inverse else actual_qty
        # For funding, we need the ABSOLUTE USD NOTIONAL.

        if self.is_inverse:
            notional_usd = p.qty  # qty IS notional for inverse in my Position record
        else:
            # Linear. We need to fetch current price or use entry? Plan says 'current_position_size'.
            # I'll use entry price for simplicity, or 1.0 if not available.
            notional_usd = p.qty * p.entry

        cost = notional_usd * rate
        self.current_equity -= cost

        logger.info(
            f"FUNDING APPLIED: Rate {rate * 100:.4f}% | Cost: ${cost:,.2f} | Equity: ${self.current_equity:,.2f}"
        )
        append_event(
            {
                "event": "FundingApplied",
                "rate": rate,
                "cost": cost,
                "equity": self.current_equity,
                "side": p.side,
                "at": ts,
            },
            paper=True,
        )

    def shutdown(self) -> None:
        """Cleanup on shutdown."""
        # 4.3 Clean Up Working Orders
        if self.working_orders:
            from laptop_agents.core.orchestrator import append_event

            for order in self.working_orders:
                logger.info(
                    f"WorkingOrderCancelled: {order.get('client_order_id', 'unknown')}"
                )
                append_event(
                    {
                        "event": "WorkingOrderCancelled",
                        "order_id": order.get("client_order_id"),
                        "side": order.get("side"),
                        "qty": order.get("qty"),
                    },
                    paper=True,
                )
            self.working_orders = []

        if self.state_path:
            self._save_state()
        logger.info("Broker shutdown complete.")

    def _process_working_orders(self, candle: Any) -> List[Dict[str, Any]]:
        """Check if any working orders can be filled."""
        fills = []
        remaining = []
        for order in self.working_orders:
            fill = self._try_fill(candle, order, is_working=True)
            if fill:
                fills.append(fill)
            else:
                remaining.append(order)
        self.working_orders = remaining
        return fills
