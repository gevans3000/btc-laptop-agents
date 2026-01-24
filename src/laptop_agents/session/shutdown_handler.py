from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, List

from laptop_agents.core.logger import logger
from laptop_agents.core.orchestrator import append_event
from laptop_agents.session.reporting import export_metrics, generate_final_reports

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


async def perform_shutdown(runner: "AsyncRunner", tasks: List[asyncio.Task]) -> None:
    """Handles the graceful shutdown sequence for the AsyncRunner."""
    if runner._shutting_down:
        return
    runner._shutting_down = True
    runner.status = "shutting_down"
    logger.info("GRACEFUL SHUTDOWN INITIATED")

    if not runner._stop_event_emitted:
        try:
            append_event(
                {
                    "event": "SessionStopped",
                    "reason": runner.stopped_reason,
                    "errors": runner.errors,
                    "symbol": runner.symbol,
                    "interval": runner.interval,
                },
                paper=True,
            )
            runner._stop_event_emitted = True
        except Exception as e:
            logger.error(f"Failed to append SessionStopped event: {e}")

    # 2. Cancel all open orders (alias in PaperBroker)
    try:
        runner.broker.cancel_all_open_orders()
    except Exception as e:
        logger.error(f"Failed to cancel orders: {e}")

    # 3. Wait up to 2s for pending fills
    try:
        await asyncio.sleep(2.0)
    except Exception:
        pass

    # 4. Queue Draining: Persist pending orders to broker state
    while not runner.execution_queue.empty():
        try:
            item = runner.execution_queue.get_nowait()
            order = item.get("order")
            if order:
                working_orders = getattr(runner.broker, "working_orders", None)
                if isinstance(working_orders, list):
                    working_orders.append(order)
                logger.info(
                    f"Drained pending order {order.get('client_order_id')} to broker state"
                )
        except asyncio.QueueEmpty:
            break

    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    # Final cleanup
    if runner.broker.pos:
        price = None
        if runner.latest_tick:
            price = runner.latest_tick.last
        elif runner.candles:
            price = runner.candles[-1].close
        if price and price > 0:
            runner.broker.close_all(price)

    try:
        # Use task wrapper for shutdown to ensure it completes
        shutdown_task = asyncio.create_task(asyncio.to_thread(runner.broker.shutdown))
        await asyncio.wait_for(asyncio.shield(shutdown_task), timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning("Broker shutdown timed out after 5s")
    except Exception as e:
        logger.exception(f"Broker shutdown failed: {e}")

    try:
        runner.state_manager.set_circuit_breaker_state(
            {"state": runner.circuit_breaker.state}
        )
        runner.state_manager.set("starting_equity", runner.starting_equity)
        runner.state_manager.save()
        logger.info("Final unified state saved.")
    except Exception as e:
        logger.error(f"Failed to save unified state on shutdown: {e}")

    # Reporting & Metrics
    export_metrics(runner)
    generate_final_reports(runner)

    logger.info("AsyncRunner shutdown complete.")
