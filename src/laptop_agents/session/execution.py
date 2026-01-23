from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from laptop_agents.constants import MAX_ERRORS_PER_SESSION
from laptop_agents.core.logger import logger
from laptop_agents.core.orchestrator import append_event

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


async def execution_task(runner: "AsyncRunner") -> None:
    """Consumes orders from execution_queue and processes them with simulated latency."""
    try:
        while not runner.shutdown_event.is_set():
            try:
                # Wait for an order with timeout so we can check shutdown
                order_payload = await asyncio.wait_for(
                    runner.execution_queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            if runner.kill_switch_triggered:
                continue

            client_order_id = None
            try:
                order = order_payload.get("order")
                candle = order_payload.get("candle")

                if not order or not order.get("go"):
                    continue

                # Item 8: Immediate ID locking
                client_order_id = order.get("client_order_id")
                if client_order_id:
                    if client_order_id in runner._inflight_order_ids:
                        logger.warning(
                            f"Duplicate order {client_order_id} detected. Skipping."
                        )
                        continue
                    runner._inflight_order_ids.add(client_order_id)

                # Simulate network latency WITHOUT blocking main loop
                if not runner.dry_run:
                    latency = order_payload.get("latency_ms", 200)
                    logger.debug(f"Executing order with {latency}ms simulated latency")
                    await asyncio.sleep(latency / 1000.0)

                # Get the CURRENT tick after latency (realistic fill price)
                current_tick = runner.latest_tick

                # Execute via broker
                events = runner.broker.on_candle(candle, order, tick=current_tick)

                for fill in events.get("fills", []):
                    runner.trades += 1
                    logger.info(f"EXECUTION FILL: {fill['side']} @ {fill['price']}")
                    append_event({"event": "ExecutionFill", **fill}, paper=True)

                for exit_event in events.get("exits", []):
                    runner.trades += 1
                    logger.info(
                        f"EXECUTION EXIT: {exit_event['reason']} @ {exit_event['price']}"
                    )
                    append_event({"event": "ExecutionExit", **exit_event}, paper=True)

                if not runner.circuit_breaker.allow_request():
                    logger.warning("CIRCUIT BREAKER OPEN")
                    runner._request_shutdown("circuit_breaker_open")

                # Save state
                if not runner.dry_run:
                    runner.state_manager.set_circuit_breaker_state(
                        {"state": runner.circuit_breaker.state}
                    )
                    runner.state_manager.save()
            except Exception as e:
                logger.exception(f"Execution task error: {e}")
                runner.errors += 1
                pos_str = runner.broker.pos.side if runner.broker.pos else "FLAT"
                open_orders_count = len(getattr(runner.broker, "working_orders", []))
                append_event(
                    {
                        "event": "ExecutionTaskError",
                        "error": str(e),
                        "symbol": runner.symbol,
                        "loop_id": runner.loop_id,
                        "position": pos_str,
                        "open_orders_count": open_orders_count,
                        "interval": runner.interval,
                    },
                    paper=True,
                )
                if (
                    runner.errors >= MAX_ERRORS_PER_SESSION
                    and not runner.shutdown_event.is_set()
                ):
                    runner._request_shutdown("error_budget")
            finally:
                if client_order_id:
                    runner._inflight_order_ids.discard(client_order_id)

    except asyncio.CancelledError:
        pass
