from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from ..core import hard_limits
from ..trading.helpers import calculate_fees, apply_slippage
from ..execution.fees import get_fee_bps
from laptop_agents.core.logger import logger
import time
import json
import random
from pathlib import Path
import shutil
from datetime import datetime, timezone


@dataclass
class Position:
    side: str  # LONG / SHORT
    entry: float
    qty: float
    sl: float
    tp: float
    opened_at: str
    entry_fees: float = 0.0
    bars_open: int = 0
    trail_active: bool = False
    trail_stop: float = 0.0


class PaperBroker:
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
    ) -> None:
        self.symbol = symbol
        self.rng = random.Random(random_seed)
        self.last_trade_time: float = 0.0
        self.min_trade_interval_sec: float = 60.0  # 1 minute minimum between trades
        self.pos: Optional[Position] = None
        self.is_inverse = self.symbol.endswith("USD") and not self.symbol.endswith(
            "USDT"
        )
        self.fees_bps = fees_bps
        self.slip_bps = slip_bps
        self.starting_equity = starting_equity
        self.current_equity = starting_equity
        self.processed_order_ids: set[str] = set()
        self.order_timestamps: List[float] = []
        self.order_history: List[Dict[str, Any]] = []
        self.state_path = state_path
        self.working_orders: List[Dict[str, Any]] = []
        if self.state_path:
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
            exit_event = self._check_exit(candle)
            if exit_event:
                events["exits"].append(exit_event)
                self.pos = None

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
                self.pos = None
                if self.state_path:
                    self._save_state()
        return events

    def _try_fill(
        self,
        candle: Any,
        order: Dict[str, Any],
        is_working: bool = False,
        tick: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        # Idempotency check
        client_order_id = order.get("client_order_id")
        if client_order_id and not is_working:
            if client_order_id in self.processed_order_ids:
                logger.warning(f"Duplicate order {client_order_id} ignored")
                from laptop_agents.core.orchestrator import append_event

                append_event(
                    {
                        "event": "OrderRejected",
                        "reason": "duplicate_order_id",
                        "order_id": client_order_id,
                    },
                    paper=True,
                )
                return None
            self.processed_order_ids.add(client_order_id)

        # Trade frequency throttle
        now = time.time()

        # Rate limiting (orders per minute)
        now = time.time()
        self.order_timestamps = [t for t in self.order_timestamps if now - t < 60]
        if len(self.order_timestamps) >= hard_limits.MAX_ORDERS_PER_MINUTE:
            logger.warning(
                f"REJECTED: Rate limit {hard_limits.MAX_ORDERS_PER_MINUTE} orders/min exceeded"
            )
            from laptop_agents.core.orchestrator import append_event

            append_event(
                {"event": "OrderRejected", "reason": "rate_limit_exceeded"}, paper=True
            )
            return None
        self.order_timestamps.append(now)

        # Daily loss check
        equity = float(order.get("equity") or self.current_equity)
        drawdown_pct = (self.starting_equity - equity) / self.starting_equity * 100.0
        if drawdown_pct > hard_limits.MAX_DAILY_LOSS_PCT:
            logger.warning(
                f"REJECTED: Daily loss {drawdown_pct:.2f}% > {hard_limits.MAX_DAILY_LOSS_PCT}%"
            )
            from laptop_agents.core.orchestrator import append_event

            append_event(
                {
                    "event": "OrderRejected",
                    "reason": "daily_loss_exceeded",
                    "drawdown_pct": drawdown_pct,
                },
                paper=True,
            )
            return None

        # HARD LIMIT ENFORCEMENT
        # Move these checks earlier to log rejection
        entry_px_est = float(candle.close)
        if entry_px_est <= 0:
            logger.error("REJECTED: Entry price estimate is zero or negative")
            return None
        qty_est = float(order["qty"])
        notional_est = qty_est * entry_px_est

        if notional_est > hard_limits.MAX_POSITION_SIZE_USD:
            logger.warning(
                f"PAPER REJECTED: Notional ${notional_est:.2f} > hard limit ${hard_limits.MAX_POSITION_SIZE_USD}"
            )
            from laptop_agents.core.orchestrator import append_event

            append_event(
                {
                    "event": "OrderRejected",
                    "reason": "notional_exceeded",
                    "notional": notional_est,
                },
                paper=True,
            )
            return None

        leverage_est = notional_est / equity
        if leverage_est > hard_limits.MAX_LEVERAGE:
            logger.warning(
                f"PAPER REJECTED: Leverage {leverage_est:.1f}x > hard limit {hard_limits.MAX_LEVERAGE}x"
            )
            from laptop_agents.core.orchestrator import append_event

            append_event(
                {
                    "event": "OrderRejected",
                    "reason": "leverage_exceeded",
                    "leverage": leverage_est,
                },
                paper=True,
            )
            return None

        entry_type = order["entry_type"]  # "limit" or "market"
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
                    f"Market Impact Penalty: {impact_pct*10000.0:.2f} bps (${impact_pct*order_notional:.2f})"
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

        # Use Dynamic Fees
        fee_bps = get_fee_bps(entry_type)
        entry_fees = calculate_fees(notional, fee_bps)

        # For Inverse, we store 'qty' as Notional USD, but the input 'qty' is in Coins.
        # So we convert it here for the Position record.
        pos_qty = notional if self.is_inverse else actual_qty

        self.pos = Position(
            side=side,
            entry=fill_px_slipped,
            qty=pos_qty,
            sl=sl,
            tp=tp,
            opened_at=candle.ts,
            entry_fees=entry_fees,
        )
        fill_event = {
            "type": "fill",
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
                "entry": fill_px,
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
        return fill_event

    def _check_tick_exit(self, tick: Any) -> Optional[Dict[str, Any]]:
        """Sub-minute check for SL/TP against latest tick price."""
        assert self.pos is not None
        p = self.pos
        px = float(tick.last)
        ts = str(tick.ts)

        if p.side == "LONG":
            if px <= p.sl:
                return self._exit(ts, p.sl, "SL_TICK")
            if px >= p.tp:
                return self._exit(ts, p.tp, "TP_TICK")
            if p.trail_active and px <= p.trail_stop:
                return self._exit(ts, p.trail_stop, "TRAIL_TICK")
        else:  # SHORT
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
                from laptop_agents.core.orchestrator import append_event

                append_event(
                    {
                        "event": "StalePosition",
                        "bars_open": self.pos.bars_open,
                        "side": self.pos.side,
                        "entry": self.pos.entry,
                    },
                    paper=True,
                )

        # ATR Trailing Stop Logic (simplified: 1.5 ATR from highest close)
        atr_mult = 1.5  # Could be configurable
        if not p.trail_active:
            # Activate trail if profit > 0.5R
            if (
                p.side == "LONG"
                and float(candle.close) > p.entry + abs(p.entry - p.sl) * 0.5
            ):
                p.trail_active = True
                p.trail_stop = float(candle.close) - abs(p.entry - p.sl) * atr_mult
                from laptop_agents.core.orchestrator import append_event

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
                from laptop_agents.core.orchestrator import append_event

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

        if self.is_inverse:
            # Inverse PnL (BTC) = Notional * (1/Entry - 1/Exit) for Long
            if p.side == "LONG":
                pnl_coins = p.qty * (1.0 / p.entry - 1.0 / px_slipped)
            else:
                pnl_coins = p.qty * (1.0 / px_slipped - 1.0 / p.entry)

            # Convert coin PnL to USD (approximate using exit price)
            pnl = pnl_coins * px_slipped

            # Inverse Risk (BTC) = Notional * |1/Entry - 1/SL|
            if p.side == "LONG":
                risk_coins = p.qty * abs(1.0 / p.entry - 1.0 / p.sl)
            else:
                risk_coins = p.qty * abs(1.0 / p.sl - 1.0 / p.entry)
            risk = risk_coins * px_slipped
        else:
            pnl = (
                (px_slipped - p.entry) * p.qty
                if p.side == "LONG"
                else (p.entry - px_slipped) * p.qty
            )
            risk = abs(p.entry - p.sl) * p.qty

        # Exits are always Taker orders
        exit_fee_bps = get_fee_bps("MARKET")
        exit_fees = calculate_fees(
            abs(p.qty * px_slipped if not self.is_inverse else p.qty), exit_fee_bps
        )
        net_pnl = pnl - exit_fees - p.entry_fees

        r_mult = (net_pnl / risk) if risk > 0 else 0.0
        self.current_equity += net_pnl
        self.order_history.append(
            {
                "type": "exit",
                "reason": reason,
                "pnl": net_pnl,
                "at": ts,
                "fees": exit_fees + p.entry_fees,
                "r": r_mult,
                "side": p.side,
            }
        )

        if self.state_path:
            self._save_state()

        return {
            "type": "exit",
            "reason": reason,
            "price": px_slipped,
            "pnl": net_pnl,
            "r": r_mult,
            "bars_open": p.bars_open,
            "at": ts,
            "fees": exit_fees + p.entry_fees,
        }

    def save_state(self) -> None:
        """Public alias for state persistence."""
        self._save_state()

    def _save_state(self) -> None:
        if not self.state_path:
            return
        state = {
            "symbol": self.symbol,
            "starting_equity": self.starting_equity,
            "current_equity": self.current_equity,
            "processed_order_ids": list(self.processed_order_ids),
            "order_history": self.order_history,
            "working_orders": self.working_orders,
            "pos": None,
            "saved_at": time.time(),  # For debugging
        }
        if self.pos:
            state["pos"] = {
                "side": self.pos.side,
                "entry": self.pos.entry,
                "qty": self.pos.qty,
                "sl": self.pos.sl,
                "tp": self.pos.tp,
                "opened_at": self.pos.opened_at,
                "entry_fees": self.pos.entry_fees,
                "bars_open": self.pos.bars_open,
                "trail_active": self.pos.trail_active,
                "trail_stop": self.pos.trail_stop,
            }

        main_path = Path(self.state_path)
        temp_path = main_path.with_suffix(".tmp")
        backup_path = main_path.with_suffix(".bak")

        try:
            # Step 1: Write to temp file
            with open(temp_path, "w") as f:
                json.dump(state, f, indent=2)

            # Step 2: Validate temp file is valid JSON
            with open(temp_path, "r") as f:
                json.load(f)  # Will raise if corrupt

            # Step 3: Backup existing state (if exists and valid)
            if main_path.exists():
                try:
                    with open(main_path, "r") as f:
                        json.load(f)  # Validate before backing up

                    shutil.copy2(main_path, backup_path)
                except (json.JSONDecodeError, Exception):
                    pass  # Don't backup corrupt files

            # Step 4: Atomic rename temp -> main
            temp_path.replace(main_path)

        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            # Clean up temp file if it exists
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    def _load_state(self) -> None:
        if not self.state_path:
            return
        path = Path(self.state_path)
        backup_path = path.with_suffix(".bak")

        # Try main file first, then backup
        for try_path, is_backup in [(path, False), (backup_path, True)]:
            if not try_path.exists():
                continue

            try:
                with open(try_path) as f:
                    state = json.load(f)

                self.starting_equity = state.get(
                    "starting_equity", self.starting_equity
                )
                self.current_equity = state.get("current_equity", self.current_equity)
                self.processed_order_ids = set(state.get("processed_order_ids", []))
                self.order_history = state.get("order_history", [])
                self.working_orders = state.get("working_orders", [])

                # Expire stale working orders (> 24 hours old)
                now = time.time()
                original_count = len(self.working_orders)
                self.working_orders = [
                    o
                    for o in self.working_orders
                    if now - o.get("created_at", now) < 86400  # 24 hours
                ]
                if original_count != len(self.working_orders):
                    logger.info(
                        f"Expired {original_count - len(self.working_orders)} stale working orders"
                    )

                pos_data = state.get("pos")
                if pos_data:
                    self.pos = Position(**pos_data)

                source = "backup" if is_backup else "primary"
                logger.info(f"Loaded broker state from {source}: {try_path}")

                # If we loaded from backup, immediately save to restore primary
                if is_backup:
                    logger.warning(
                        "Loaded from BACKUP. Primary was corrupt. Restoring primary file..."
                    )
                    self._save_state()

                return  # Success - exit the loop

            except json.JSONDecodeError as e:
                logger.error(f"State file corrupt ({try_path}): {e}")
                # Rename corrupt file for debugging
                corrupt_path = try_path.with_suffix(f".corrupt.{int(time.time())}")
                try:
                    try_path.rename(corrupt_path)
                    logger.warning(f"Renamed corrupt file to {corrupt_path}")
                except Exception:
                    pass
                continue  # Try next file

            except Exception as e:
                logger.error(f"Failed to load broker state from {try_path}: {e}")
                continue

        # If we get here, no valid state was found
        logger.warning("No valid state file found. Starting with fresh state.")

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

    def close_all(self, current_price: float) -> List[Dict[str, Any]]:
        """Force close any open positions."""
        if self.pos is None:
            return []
        logger.info(f"FORCED CLOSE OF {self.pos.side} @ {current_price}")
        exit_event = self._exit(
            datetime.now(timezone.utc).isoformat(), current_price, "FORCE_CLOSE"
        )
        self.pos = None
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
            f"FUNDING APPLIED: Rate {rate*100:.4f}% | Cost: ${cost:,.2f} | Equity: ${self.current_equity:,.2f}"
        )
        from laptop_agents.core.orchestrator import append_event

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
            if self.pos is None:  # Only fill if no position
                # We need to bypass the client_order_id check for working orders
                # as they are already processed.
                fill = self._try_fill(candle, order, is_working=True)
                if fill:
                    fills.append(fill)
                else:
                    remaining.append(order)
            else:
                remaining.append(order)
        self.working_orders = remaining
        return fills
