"""Session lifecycle management: run loop and shutdown coordination."""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, List

from laptop_agents.core.logger import logger
from laptop_agents.session.heartbeat import heartbeat_task
from laptop_agents.session.funding import funding_task
from laptop_agents.session.execution import execution_task
from laptop_agents.session.stale_data import stale_data_task
from laptop_agents.session.watchdog import watchdog_tick_task, hardware_watchdog_thread
from laptop_agents.session.kill_switch import kill_switch_task
from laptop_agents.session.timer import timer_task
from laptop_agents.session.checkpoint import checkpoint_task
from laptop_agents.session.market_data import market_data_task
from laptop_agents.session.seeding import seed_historical_candles

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


async def run_session_lifecycle(runner: "AsyncRunner", duration_min: int) -> None:
    """Main entry point to run the async trading loop.

    Manages:
    - Circuit breaker check
    - Hardware watchdog thread (frozen loop detection)
    - Historical candle seeding
    - Async task orchestration
    - Graceful shutdown
    """
    runner.duration_min = duration_min
    end_time = runner.start_time + (duration_min * 60)
    runner.status = "running"

    # Check circuit breaker state
    if not runner.circuit_breaker.allow_request():
        logger.warning("Circuit breaker is OPEN. It remains OPEN.")
        request_shutdown(runner, "circuit_breaker_open")

    # Start Hardware Watchdog Thread (independent of event loop for frozen-loop detection)
    watchdog_thread = threading.Thread(
        target=hardware_watchdog_thread, args=(runner,), daemon=True
    )
    watchdog_thread.start()
    logger.info("Hardware watchdog thread started.")

    # Seed historical candles
    await seed_historical_candles(runner)

    # Start async tasks
    tasks = [
        asyncio.create_task(market_data_task(runner)),
        asyncio.create_task(watchdog_tick_task(runner)),
        asyncio.create_task(heartbeat_task(runner)),
        asyncio.create_task(timer_task(runner, end_time)),
        asyncio.create_task(kill_switch_task(runner)),
        asyncio.create_task(stale_data_task(runner)),
        asyncio.create_task(funding_task(runner)),
        asyncio.create_task(execution_task(runner)),
        asyncio.create_task(checkpoint_task(runner)),
    ]
    for task in tasks:
        task.add_done_callback(lambda t: handle_task_done(runner, t))

    try:
        await runner.shutdown_event.wait()
    finally:
        await perform_shutdown(runner, tasks)


async def perform_shutdown(runner: "AsyncRunner", tasks: List[asyncio.Task]) -> None:
    """Delegates shutdown to the external handler."""
    from laptop_agents.session.shutdown_handler import (
        perform_shutdown as _perform_shutdown,
    )

    await _perform_shutdown(runner, tasks)


def request_shutdown(runner: "AsyncRunner", reason: str) -> None:
    """Request a graceful shutdown with the given reason."""
    if not runner.shutdown_event.is_set():
        if runner.stopped_reason == "completed":
            runner.stopped_reason = reason
        runner.shutdown_event.set()


def handle_task_done(runner: "AsyncRunner", task: asyncio.Task) -> None:
    """Callback for task completion, handles exceptions."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error(f"Task failed: {task.get_name()} | {exc}")
        runner.errors += 1
        request_shutdown(runner, "task_failed")
