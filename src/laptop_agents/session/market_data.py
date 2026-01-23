from __future__ import annotations

import asyncio
import math
import random
import time
from typing import TYPE_CHECKING

from laptop_agents import constants as hard_limits
from laptop_agents.constants import MAX_ERRORS_PER_SESSION
from laptop_agents.core.logger import logger, write_alert
from laptop_agents.trading.helpers import (
    normalize_candle_order,
    Candle,
    Tick,
    DataEvent,
)
from laptop_agents.data.providers.bitunix_futures import (
    BitunixFuturesProvider,
    FatalError,
)
from laptop_agents.session.strategy import on_candle_closed

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


async def market_data_task(runner: "AsyncRunner") -> None:
    """Consumes WebSocket data and triggers strategy on candle closure."""
    while not runner.shutdown_event.is_set():
        listener = None
        try:
            listener = runner.provider.listen()
            while not runner.shutdown_event.is_set():
                try:
                    # Item 1: Timeout-aware iteration
                    item = await asyncio.wait_for(listener.__anext__(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue
                except StopAsyncIteration:
                    break

                if isinstance(item, DataEvent):
                    logger.warning(
                        f"RECEIVED_DATA_EVENT: {item.event} | {item.details}"
                    )
                    if item.event in ["ORDER_BOOK_STALE", "CIRCUIT_TRIPPED"]:
                        write_alert(f"MARKET_DATA_FAILED: {item.event}")
                        runner._request_shutdown("market_data_failed")
                        break

                if isinstance(item, Tick):
                    ts_sec = runner._parse_ts_to_int(item.ts)
                    if ts_sec <= 0:
                        continue
                    last_ts_sec = (
                        runner._parse_ts_to_int(runner.last_tick_ts)
                        if runner.last_tick_ts
                        else 0
                    )
                    if ts_sec <= last_ts_sec:
                        continue
                    if (time.time() - ts_sec) > runner.stale_data_timeout_sec:
                        continue
                    # Robust Validation
                    bid = getattr(item, "bid", None)
                    ask = getattr(item, "ask", None)
                    last = getattr(item, "last", None)
                    if bid is None or ask is None or last is None:
                        continue
                    if any((not math.isfinite(x)) or x <= 0 for x in [bid, ask, last]):
                        continue
                    if bid > ask:
                        continue

                    runner.latest_tick = item
                    runner.last_tick_ts = item.ts
                    runner.last_data_time = time.time()
                    runner.stale_restart_attempts = 0
                    runner.consecutive_ws_errors = 0

                elif isinstance(item, Candle):
                    ts_sec = runner._parse_ts_to_int(item.ts)
                    if ts_sec <= 0:
                        continue
                    last_ts_sec = (
                        runner._parse_ts_to_int(runner.last_candle_ts)
                        if runner.last_candle_ts
                        else 0
                    )
                    if ts_sec <= last_ts_sec:
                        continue
                    if (time.time() - ts_sec) > runner.stale_data_timeout_sec:
                        continue
                    open_val = getattr(item, "open", None)
                    high_val = getattr(item, "high", None)
                    low_val = getattr(item, "low", None)
                    close_val = getattr(item, "close", None)
                    if (
                        open_val is None
                        or high_val is None
                        or low_val is None
                        or close_val is None
                    ):
                        continue
                    if any(
                        (not math.isfinite(x)) or x <= 0
                        for x in [open_val, high_val, low_val, close_val]
                    ):
                        continue
                    if low_val > high_val:
                        continue
                    volume_val = getattr(item, "volume", None)
                    if volume_val is not None:
                        if (not math.isfinite(volume_val)) or volume_val < 0:
                            continue

                    runner.consecutive_ws_errors = 0
                    runner.last_candle_ts = item.ts
                    runner.last_data_time = time.time()
                    runner.stale_restart_attempts = 0
                    new_ts_sec = ts_sec

                    # Item 3 & 12: Fixed Gap-Detection & Rate Limiting
                    try:
                        interval_sec = {
                            "1m": 60,
                            "5m": 300,
                            "15m": 900,
                            "1h": 3600,
                        }.get(runner.interval, 60)
                        if runner.candles:
                            last_ts_sec = runner._parse_ts_to_int(runner.candles[-1].ts)
                            if (new_ts_sec - last_ts_sec) > interval_sec * 1.5:
                                missing_count = int(
                                    (new_ts_sec - last_ts_sec) / interval_sec
                                )
                                now = time.time()
                                if (
                                    missing_count > 0
                                    and (now - runner._last_backfill_time) >= 30.0
                                ):
                                    logger.warning(
                                        f"GAP_DETECTED: {missing_count} missing. Backfilling..."
                                    )
                                    try:
                                        fetched = await asyncio.to_thread(
                                            BitunixFuturesProvider.load_rest_candles,
                                            runner.symbol,
                                            runner.interval,
                                            min(missing_count + 5, 200),
                                        )
                                        runner._last_backfill_time = (
                                            time.time()
                                        )  # Update AFTER success
                                        fetched = normalize_candle_order(fetched)
                                        for f_candle in fetched:
                                            f_ts_sec = runner._parse_ts_to_int(
                                                f_candle.ts
                                            )
                                            if last_ts_sec < f_ts_sec < new_ts_sec:
                                                if f_candle.ts not in [
                                                    c.ts for c in runner.candles
                                                ]:
                                                    runner.candles.append(f_candle)
                                        runner.candles.sort(
                                            key=lambda x: runner._parse_ts_to_int(x.ts)
                                        )
                                    except Exception as be:
                                        pos_str = (
                                            runner.broker.pos.side
                                            if runner.broker.pos
                                            else "FLAT"
                                        )
                                        open_orders_count = len(
                                            getattr(runner.broker, "working_orders", [])
                                        )
                                        logger.exception(
                                            "Backfill failed",
                                            {
                                                "event": "BackfillError",
                                                "symbol": runner.symbol,
                                                "loop_id": runner.loop_id,
                                                "position": pos_str,
                                                "open_orders_count": open_orders_count,
                                                "interval": runner.interval,
                                                "error": str(be),
                                            },
                                        )
                    except Exception as ge:
                        pos_str = (
                            runner.broker.pos.side if runner.broker.pos else "FLAT"
                        )
                        open_orders_count = len(
                            getattr(runner.broker, "working_orders", [])
                        )
                        logger.exception(
                            "Error checking for gaps",
                            {
                                "event": "GapCheckError",
                                "symbol": runner.symbol,
                                "loop_id": runner.loop_id,
                                "position": pos_str,
                                "open_orders_count": open_orders_count,
                                "interval": runner.interval,
                                "error": str(ge),
                            },
                        )

                    if not runner.candles or item.ts != runner.candles[-1].ts:
                        if runner.candles:
                            await on_candle_closed(runner, runner.candles[-1])
                        runner.candles.append(item)
                        if len(runner.candles) > hard_limits.MAX_CANDLE_BUFFER:
                            runner.candles = runner.candles[
                                -hard_limits.MAX_CANDLE_BUFFER :
                            ]
                    else:
                        runner.candles[-1] = item

        except asyncio.CancelledError:
            break  # Exit cleanly on cancel
        except FatalError as fe:
            pos_str = runner.broker.pos.side if runner.broker.pos else "FLAT"
            open_orders_count = len(getattr(runner.broker, "working_orders", []))
            logger.exception(
                "FATAL_ERROR in market_data_task",
                {
                    "event": "MarketDataFatal",
                    "symbol": runner.symbol,
                    "loop_id": runner.loop_id,
                    "position": pos_str,
                    "open_orders_count": open_orders_count,
                    "interval": runner.interval,
                    "error": str(fe),
                },
            )
            runner.errors = MAX_ERRORS_PER_SESSION
            runner._request_shutdown("fatal_error")
            break
        except Exception as e:
            # Item 1: Graceful restart instead of hard fail
            if runner.shutdown_event.is_set():
                break

            runner.errors += 1
            runner.consecutive_ws_errors += 1
            pos_str = runner.broker.pos.side if runner.broker.pos else "FLAT"
            open_orders_count = len(getattr(runner.broker, "working_orders", []))
            logger.exception(
                "Error in market data stream",
                {
                    "event": "MarketDataError",
                    "symbol": runner.symbol,
                    "loop_id": runner.loop_id,
                    "position": pos_str,
                    "open_orders_count": open_orders_count,
                    "interval": runner.interval,
                    "attempt": runner.consecutive_ws_errors,
                    "error": str(e),
                },
            )

            if runner.consecutive_ws_errors >= 10:
                if not runner.shutdown_event.is_set():
                    logger.critical("Too many consecutive WS errors. Giving up.")
                    runner._request_shutdown("market_data_errors")
                break

            # Exponential backoff + jitter (cap at 60s)
            backoff = min(60.0, 2 ** min(runner.consecutive_ws_errors, 6))
            jitter = random.uniform(0.0, 1.0)
            await asyncio.sleep(backoff + jitter)
        finally:
            if listener is not None:
                try:
                    await listener.aclose()
                except asyncio.CancelledError:
                    pass
                except Exception as close_err:
                    pos_str = runner.broker.pos.side if runner.broker.pos else "FLAT"
                    open_orders_count = len(
                        getattr(runner.broker, "working_orders", [])
                    )
                    logger.exception(
                        "Failed to close market data listener",
                        {
                            "event": "MarketDataListenerCloseError",
                            "symbol": runner.symbol,
                            "loop_id": runner.loop_id,
                            "position": pos_str,
                            "open_orders_count": open_orders_count,
                            "interval": runner.interval,
                            "error": str(close_err),
                        },
                    )
