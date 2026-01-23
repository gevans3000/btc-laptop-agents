from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from laptop_agents import constants as hard_limits
from laptop_agents.core.logger import logger
from laptop_agents.core.orchestrator import append_event
from laptop_agents.trading.helpers import normalize_candle_order
from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


async def stale_data_task(runner: "AsyncRunner") -> None:
    """Detects stale market data and triggers task restart or shutdown."""
    try:
        restart_threshold = min(30.0, runner.stale_data_timeout_sec)
        while not runner.shutdown_event.is_set():
            age = time.time() - runner.last_data_time

            # Soft restart if data is hanging for more than 15 seconds
            if age > 15.0:
                logger.warning(f"STALE DATA: No market data for {age:.1f}s.")
                # Attempt REST poll as a fallback signal when WS is unhealthy
                now = time.time()
                if now - runner._last_rest_poll_time >= 15.0:
                    try:
                        candles = await asyncio.to_thread(
                            BitunixFuturesProvider.load_rest_candles,
                            runner.symbol,
                            runner.interval,
                            2,
                        )
                        candles = normalize_candle_order(candles)
                        if candles:
                            latest = candles[-1]
                            latest_ts = runner._parse_ts_to_int(latest.ts)
                            last_ts = (
                                runner._parse_ts_to_int(runner.last_candle_ts)
                                if runner.last_candle_ts
                                else 0
                            )
                            if latest_ts > last_ts:
                                runner.candles.append(latest)
                                if len(runner.candles) > hard_limits.MAX_CANDLE_BUFFER:
                                    runner.candles = runner.candles[
                                        -hard_limits.MAX_CANDLE_BUFFER :
                                    ]
                                runner.last_candle_ts = latest.ts
                            runner.last_data_time = time.time()
                            runner._last_rest_poll_time = now
                            logger.info(
                                "REST_POLL_SUCCESS: refreshed candle from REST",
                                {
                                    "event": "RestPollSuccess",
                                    "symbol": runner.symbol,
                                    "loop_id": runner.loop_id,
                                    "position": (
                                        runner.broker.pos.side
                                        if runner.broker.pos
                                        else "FLAT"
                                    ),
                                    "open_orders_count": len(
                                        getattr(runner.broker, "working_orders", [])
                                    ),
                                    "interval": runner.interval,
                                },
                            )
                    except Exception as re:
                        logger.warning(f"REST poll failed during stale data: {re}")
                    finally:
                        runner._last_rest_poll_time = now

            if age > restart_threshold:
                if runner.shutdown_event.is_set():
                    break  # Already shutting down
                if runner.stale_restart_attempts < runner.max_stale_restarts:
                    runner.stale_restart_attempts += 1
                    logger.error(
                        "STALE DATA: No market data for %.0fs. Attempting provider restart (%d/%d).",
                        age,
                        runner.stale_restart_attempts,
                        runner.max_stale_restarts,
                    )
                    append_event(
                        {
                            "event": "StaleDataRestart",
                            "error": f"no market data for {age:.0f}s",
                            "attempt": runner.stale_restart_attempts,
                            "symbol": runner.symbol,
                            "interval": runner.interval,
                        },
                        paper=True,
                    )
                    try:
                        if runner.provider and hasattr(runner.provider, "client"):
                            runner.provider.client.stop()
                            await asyncio.sleep(1.0)
                            runner.provider.client.start()
                        elif (
                            runner.provider
                            and hasattr(runner.provider, "stop")
                            and hasattr(runner.provider, "start")
                        ):
                            runner.provider.stop()
                            await asyncio.sleep(1.0)
                            runner.provider.start()
                        runner.last_data_time = time.time()
                        runner.consecutive_ws_errors = 0
                    except Exception as re:
                        logger.error(f"Provider restart failed: {re}")
                        runner.errors += 1
                elif age > runner.stale_data_timeout_sec:
                    error_msg = (
                        f"STALE DATA: No market data for {age:.0f}s. "
                        "Restart attempts exhausted."
                    )
                    logger.error(error_msg)
                    runner.errors += 1
                    # Ensure final report reflects this error
                    append_event(
                        {
                            "event": "StaleDataError",
                            "error": error_msg,
                            "symbol": runner.symbol,
                            "interval": runner.interval,
                        },
                        paper=True,
                    )
                    runner._request_shutdown("stale_data")
                    break

            # Check data liveness
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        pass
