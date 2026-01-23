from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from laptop_agents.core.logger import logger

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


async def timer_task(runner: "AsyncRunner", end_time: float) -> None:
    """Triggers shutdown after duration_limit."""
    try:
        while time.time() < end_time:
            await asyncio.sleep(1.0)
        logger.info("Duration limit reached. Shutting down...")
        runner._request_shutdown("duration_limit")
    except asyncio.CancelledError:
        pass
