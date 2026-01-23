from __future__ import annotations

import asyncio
import math
import random
import time
import uuid
from typing import TYPE_CHECKING, Any

from laptop_agents.constants import MAX_ERRORS_PER_SESSION
from laptop_agents.core.logger import logger
from laptop_agents.core.orchestrator import append_event
from laptop_agents.trading.helpers import Candle

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


def safe_float(value: Any, default: float) -> float:
    """Helper to safely convert values to float."""
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


async def on_candle_closed(runner: "AsyncRunner", candle: Candle) -> None:
    """Runs strategy logic when a candle is confirmed closed."""
    if math.isnan(candle.close) or candle.close <= 0:
        return
    runner.iterations += 1
    warmup_bars = (
        runner.strategy_config.get("warmup_bars", 50) if runner.strategy_config else 50
    )

    # Item 11: Unified Warmup Guard
    if len(runner.candles) < warmup_bars:
        if runner.iterations % 10 == 0:
            logger.info(f"WARMUP_IN_PROGRESS: {len(runner.candles)}/{warmup_bars} bars")
        return
    elif len(runner.candles) == warmup_bars:
        logger.info("WARMUP_COMPLETE: Strategy active.")

    try:
        # Generate signal
        order = None

        if runner.strategy_config:
            try:
                # Use persistent supervisor and state for high performance
                runner.agent_state.candles = runner.candles[:-1]
                runner.agent_state = runner.supervisor.step(
                    runner.agent_state, candle, skip_broker=True
                )
            except Exception as agent_err:
                pos_str = runner.broker.pos.side if runner.broker.pos else "FLAT"
                open_orders_count = len(getattr(runner.broker, "working_orders", []))
                logger.exception(
                    "AGENT_ERROR: Strategy agent failed, skipping signal",
                    {
                        "event": "AgentError",
                        "symbol": runner.symbol,
                        "loop_id": runner.loop_id,
                        "position": pos_str,
                        "open_orders_count": open_orders_count,
                        "interval": runner.interval,
                        "error": str(agent_err),
                    },
                )
                append_event(
                    {"event": "AgentError", "error": str(agent_err)}, paper=True
                )
                runner.errors += 1
                return

        agent_order = runner.agent_state.order if runner.strategy_config else {}
        if (
            runner.kill_switch_triggered
            or runner.shutdown_event.is_set()
            or not runner.circuit_breaker.allow_request()
        ):
            agent_order = {}
        if agent_order and agent_order.get("go"):
            entry = safe_float(agent_order.get("entry"), candle.close)
            qty = safe_float(agent_order.get("qty"), 0.0)
            sl = safe_float(agent_order.get("sl"), 0.0)
            tp = safe_float(agent_order.get("tp"), 0.0)
            order_symbol = agent_order.get("symbol") or runner.symbol

            if order_symbol != runner.symbol:
                logger.warning("ORDER_REJECTED: Symbol mismatch")
                append_event(
                    {
                        "event": "OrderRejected",
                        "reason": "symbol_mismatch",
                        "symbol": order_symbol,
                        "expected_symbol": runner.symbol,
                    },
                    paper=True,
                )
                order = None
            else:
                order = {
                    "go": True,
                    "side": agent_order.get("side"),
                    "symbol": order_symbol,
                    "entry_type": agent_order.get("entry_type", "market"),
                    "entry": entry,
                    "qty": qty,
                    "sl": sl,
                    "tp": tp,
                    "equity": runner.broker.current_equity,
                    "client_order_id": f"async_{uuid.uuid4().hex}",
                }

                if order["side"] not in {"LONG", "SHORT"}:
                    logger.warning("ORDER_REJECTED: Invalid side")
                    order = None
                elif order["sl"] <= 0 or order["tp"] <= 0:
                    logger.warning("ORDER_REJECTED: Non-positive SL/TP")
                    order = None
                elif not all(
                    math.isfinite(x)
                    for x in [
                        order["entry"],
                        order["qty"],
                        order["sl"],
                        order["tp"],
                    ]
                ):
                    logger.warning("ORDER_REJECTED: Non-finite order fields")
                    order = None
                elif order["qty"] <= 0:
                    logger.warning("ORDER_REJECTED: Non-positive quantity")
                    order = None
                else:
                    if order["side"] == "LONG":
                        if not (order["sl"] < order["entry"] < order["tp"]):
                            logger.warning(
                                "ORDER_REJECTED: Invalid LONG SL/TP ordering"
                            )
                            order = None
                    elif order["side"] == "SHORT":
                        if not (order["tp"] < order["entry"] < order["sl"]):
                            logger.warning(
                                "ORDER_REJECTED: Invalid SHORT SL/TP ordering"
                            )
                            order = None

        # Queue order for async execution (non-blocking)
        if order and order.get("go"):
            latency_ms = random.randint(50, 500)
            logger.info(f"Queuing order for execution (latency: {latency_ms}ms)")
            try:
                runner.execution_queue.put_nowait(
                    {
                        "order": order,
                        "candle": candle,
                        "latency_ms": latency_ms,
                        "queued_at": time.time(),
                    }
                )
            except asyncio.QueueFull:
                logger.error("EXECUTION_QUEUE_FULL: Order dropped!")
                append_event(
                    {"event": "OrderDropped", "reason": "queue_full"}, paper=True
                )
                runner.errors += 1
                if (
                    runner.errors >= MAX_ERRORS_PER_SESSION
                    and not runner.shutdown_event.is_set()
                ):
                    logger.error(
                        f"ERROR BUDGET EXHAUSTED: {runner.errors} errors. Shutting down."
                    )
                    runner._request_shutdown("error_budget")
        else:
            # Still process candle for exits on existing positions
            events = runner.broker.on_candle(candle, None, tick=runner.latest_tick)
            for exit_event in events.get("exits", []):
                runner.trades += 1
                logger.info(
                    f"CANDLE EXIT: {exit_event['reason']} @ {exit_event['price']}"
                )
                append_event({"event": "CandleExit", **exit_event}, paper=True)

    except Exception as e:
        logger.exception(f"Error in on_candle_closed: {e}")
        runner.errors += 1
        if (
            runner.errors >= MAX_ERRORS_PER_SESSION
            and not runner.shutdown_event.is_set()
        ):
            logger.error(
                f"ERROR BUDGET EXHAUSTED: {runner.errors} errors. Shutting down."
            )
            runner._request_shutdown("error_budget")
