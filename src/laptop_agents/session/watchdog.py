from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from laptop_agents.constants import MAX_ERRORS_PER_SESSION
from laptop_agents.core.logger import logger
from laptop_agents.core.orchestrator import append_event

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


async def watchdog_tick_task(runner: "AsyncRunner") -> None:
    """Checks open positions against latest tick every 50ms (REALTIME SENTINEL)."""
    try:
        while not runner.shutdown_event.is_set():
            if runner.latest_tick and runner.broker.pos:
                # Item 4: Exception guard for watchdog logic
                try:
                    events = runner.broker.on_tick(runner.latest_tick) or {}
                    for exit_event in events.get("exits", []):
                        runner.trades += 1
                        logger.info(
                            f"REALTIME_TICK_EXIT: {exit_event['reason']} @ {exit_event['price']}"
                        )
                        runner.metrics.append(
                            {
                                "ts": datetime.now(timezone.utc).isoformat(),
                                "elapsed": time.time() - runner.start_time,
                                "equity": runner.broker.current_equity,
                                "price": exit_event["price"],
                                "unrealized": 0.0,
                                "event": "REALTIME_TICK_EXIT",
                                "reason": exit_event["reason"],
                            }
                        )
                        append_event(
                            {
                                "event": "WatchdogExit",
                                "tick": vars(runner.latest_tick),
                                **exit_event,
                            },
                            paper=True,
                        )
                except Exception as e:
                    logger.error(f"Error in watchdog on_tick: {e}")
                    # runner.errors += 1 # Already in runner._request_shutdown if needed
                    if runner.errors >= MAX_ERRORS_PER_SESSION:
                        runner._request_shutdown("error_budget")
            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        pass


def hardware_watchdog_thread(runner: "AsyncRunner") -> None:
    """Independent thread that kills the process if main loop freezes."""
    import psutil
    import os

    process = psutil.Process()
    while not runner.shutdown_event.is_set():
        if runner.shutdown_event.is_set():
            break
        age = time.time() - runner.last_heartbeat_time
        # Item 14: Increased threshold and graceful attempt
        if age > 60:
            print(f"\n\n!!! WATCHDOG FATAL: Main loop frozen for {age:.1f}s. !!!\n\n")
            logger.critical(f"WATCHDOG_FATAL: Main loop frozen for {age:.1f}s.")
            runner._request_shutdown("watchdog_frozen")
            time.sleep(5)  # Give it 5s to shut down gracefully
            os._exit(1)

        # Memory check (Phase 4.1)
        try:
            mem_rss_mb = process.memory_info().rss / 1024 / 1024
            # Use LA_MAX_MEMORY_MB for hardware watchdog as well
            max_mem_allowed = float(os.getenv("LA_MAX_MEMORY_MB", "1500"))
            if mem_rss_mb > max_mem_allowed:
                print(
                    f"\n\n!!! CRITICAL: Memory Limit Exceeded ({mem_rss_mb:.1f} MB). FORCE EXITing. !!!\n\n"
                )
                logger.critical(
                    f"CRITICAL: Memory Limit Exceeded ({mem_rss_mb:.1f} MB). RSS > {max_mem_allowed} MB."
                )
                runner._request_shutdown("memory_limit")
                os._exit(1)
        except (OSError, PermissionError, psutil.Error) as e:
            logger.debug(f"Hardware watchdog suppressed minor error: {e}")

        time.sleep(1)
