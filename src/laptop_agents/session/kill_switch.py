from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

from laptop_agents.core.logger import logger

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


async def kill_switch_task(runner: "AsyncRunner") -> None:
    """Monitors for kill.txt file to trigger emergency shutdown."""
    try:
        while not runner.shutdown_event.is_set():
            if runner.kill_file.exists() or os.getenv("LA_KILL_SWITCH") == "TRUE":
                reason = (
                    "kill.txt detected"
                    if runner.kill_file.exists()
                    else "LA_KILL_SWITCH=TRUE"
                )
                logger.warning(f"KILL SWITCH ACTIVATED: {reason}")
                runner._request_shutdown("kill_switch")
                if runner.kill_file.exists():
                    try:
                        runner.kill_file.unlink()  # Remove file after processing
                    except Exception:
                        pass
                # Special exit code for kill switch as requested in plan (though we are in async task)
                # We'll set a flag to exit with 99 in the main block
                runner.kill_switch_triggered = True
                break
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass
