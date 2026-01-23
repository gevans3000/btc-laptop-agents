from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from laptop_agents.core.logger import logger

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


async def funding_task(runner: "AsyncRunner") -> None:
    """Checks for 8-hour funding windows (00:00, 08:00, 16:00 UTC)."""
    # Initialize last_funding_hour to current hour to avoid instant charge on startup if within window
    now = datetime.now(timezone.utc)
    last_funding_hour = now.hour if now.minute == 0 else None

    try:
        while not runner.shutdown_event.is_set():
            now = datetime.now(timezone.utc)
            # Funding windows: 00:00, 08:00, 16:00 UTC
            if (
                now.hour in [0, 8, 16]
                and now.minute == 0
                and now.hour != last_funding_hour
            ):
                logger.info(f"Funding window detected at {now.hour:02d}:00 UTC")
                if (
                    runner.provider
                    and hasattr(runner.provider, "funding_rate")
                    and asyncio.iscoroutinefunction(runner.provider.funding_rate)
                ):
                    try:
                        rate = await runner.provider.funding_rate()
                        logger.info(f"FUNDING APPLIED: Rate {rate:.6f}")
                        runner.broker.apply_funding(rate, now.isoformat())
                    except Exception as fe:
                        logger.warning(f"Failed to fetch/apply funding rate: {fe}")
                else:
                    logger.debug("Provider does not support funding_rate(). Skipping.")
                last_funding_hour = now.hour

            if now.minute != 0:
                last_funding_hour = None

            await asyncio.sleep(30)
    except asyncio.CancelledError:
        pass
