from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from laptop_agents.core.logger import logger

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


async def checkpoint_task(runner: "AsyncRunner") -> None:
    """Periodically saves state to disk for crash recovery."""
    try:
        while not runner.shutdown_event.is_set():
            await asyncio.sleep(60)
            try:
                # Item 13: Offload checkpointing to threads
                def do_checkpoint():
                    runner.state_manager.set_circuit_breaker_state(
                        {"state": runner.circuit_breaker.state}
                    )
                    runner.state_manager.set("starting_equity", runner.starting_equity)
                    runner.state_manager.save()
                    runner.broker.save_state()

                await asyncio.to_thread(do_checkpoint)
                logger.info("Pulse checkpoint saved.")
            except Exception as e:
                pos_str = runner.broker.pos.side if runner.broker.pos else "FLAT"
                open_orders_count = len(getattr(runner.broker, "working_orders", []))
                logger.exception(
                    "Checkpoint failed",
                    {
                        "event": "CheckpointError",
                        "symbol": runner.symbol,
                        "loop_id": runner.loop_id,
                        "position": pos_str,
                        "open_orders_count": open_orders_count,
                        "interval": runner.interval,
                        "error": str(e),
                    },
                )
    except asyncio.CancelledError:
        pass
