from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from laptop_agents.core.logger import logger
from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider
from laptop_agents.trading.helpers import normalize_candle_order, detect_candle_gaps

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


async def seed_historical_candles(runner: "AsyncRunner") -> None:
    """Pre-loads historical candles to seed the strategy."""
    min_history = 100
    if runner.strategy_config:
        min_history = runner.strategy_config.get("engine", {}).get(
            "min_history_bars", 100
        )

    if hasattr(runner.provider, "history"):
        logger.info(
            f"Seeding historical candles from provider (count={min_history})..."
        )
        runner.candles = runner.provider.history(min_history)
    else:
        retry_count = 0
        while retry_count < 5:
            try:
                logger.info(
                    f"Seeding historical candles via REST (attempt {retry_count + 1}/5)..."
                )
                runner.candles = BitunixFuturesProvider.load_rest_candles(
                    runner.symbol, runner.interval, limit=max(100, min_history)
                )
                runner.candles = normalize_candle_order(runner.candles)

                if len(runner.candles) >= min_history:
                    logger.info(f"Seed complete: {len(runner.candles)} candles")
                    break
                else:
                    logger.warning(
                        f"Incomplete seed: {len(runner.candles)}/{min_history}. Retrying in 10s..."
                    )
            except Exception as e:
                logger.warning(f"Seed attempt {retry_count + 1} failed: {e}")

            retry_count += 1
            if retry_count < 5:
                # Wait before retry
                await asyncio.sleep(10)

        if len(runner.candles) < min_history:
            logger.error(
                f"DEGRADED_START: Failed to seed historical candles after 5 attempts "
                f"({len(runner.candles)} < {min_history}). Starting with empty/partial history."
            )
            if runner.candles is None:
                runner.candles = []
        else:
            logger.info(f"Seed complete: {len(runner.candles)} candles")

    # Detect gaps in historical data
    gaps = detect_candle_gaps(runner.candles, runner.interval)
    for gap in gaps:
        logger.warning(
            f"GAP_DETECTED: {gap['missing_count']} missing between {gap['prev_ts']} and {gap['curr_ts']}"
        )
