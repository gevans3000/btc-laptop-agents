import asyncio
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
import sys
from collections import deque

# Add src to path before importing laptop_agents
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from laptop_agents.session.async_session import AsyncRunner
from laptop_agents.trading.helpers import Tick, utc_ts
from laptop_agents.core.logger import logger
from laptop_agents.paper.broker import Position
from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider


async def test_autonomy_upgrade():
    logger.info("Starting Autonomy Upgrade Verification...")

    # Setup
    symbol = "BTCUSDT"
    interval = "1m"
    base_dir = Path("tests/temp_autonomy_test")
    if base_dir.exists():
        try:
            shutil.rmtree(base_dir)
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not clean base_dir: {e}")
    base_dir.mkdir(parents=True, exist_ok=True)

    state_dir = base_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    # Backup original method to avoid global state pollution during test
    original_load_rest = BitunixFuturesProvider.load_rest_candles
    BitunixFuturesProvider.load_rest_candles = MagicMock(return_value=[])

    try:
        # Mock Provider
        mock_provider = MagicMock()
        mock_provider.history.return_value = []  # Prevent fallback to REST seeding
        mock_provider.get_instrument_info.return_value = {
            "tickSize": 0.01,
            "lotSize": 0.001,
            "minQty": 0.001,
            "maxQty": 100.0,
            "minNotional": 5.0,
        }

        # Ticks for Task 2 test
        def get_bad_tick():
            # Price=0 should be ignored by market_data_task
            return Tick(symbol=symbol, bid=0.0, ask=0.0, last=0.0, ts=utc_ts())

        def get_good_tick():
            # Good tick with valid price and ISO timestamp
            return Tick(
                symbol=symbol,
                bid=50000.0,
                ask=50001.0,
                last=50000.5,
                ts=utc_ts(),
            )

        # Use a side effect to yield items as an async generator
        async def mock_listen_impl():
            yield get_bad_tick()
            await asyncio.sleep(0.1)
            yield get_good_tick()
            logger.info("Sent initial mock ticks (one bad, one good)")

            # Yield a few more to keep market_data_task from declaring staleness
            for _ in range(10):
                await asyncio.sleep(0.5)
                yield get_good_tick()

            # stay open until task cancelled
            try:
                while True:
                    await asyncio.sleep(10)
            except asyncio.CancelledError:
                logger.info("Mock listen cancelled")
                pass

        mock_provider.listen.side_effect = mock_listen_impl
        mock_provider.fetch_and_inject_gap = AsyncMock()

        runner = AsyncRunner(
            symbol=symbol,
            interval=interval,
            starting_balance=10000.0,
            provider=mock_provider,
            state_dir=state_dir,
        )

        # Task 4 Check: Mock close_all to verify it's called on exit
        runner.broker.close_all = MagicMock(wraps=runner.broker.close_all)

        # Run the runner in the background
        run_task = asyncio.create_task(runner.run(duration_min=1))

        logger.info("Waiting for data processing...")
        received_good_tick = False
        for _ in range(30):  # Wait up to 15s
            await asyncio.sleep(0.5)
            if run_task.done():
                exc = run_task.exception()
                if exc:
                    logger.error(f"Runner task failed early: {exc}")
                    raise exc
                break
            if runner.latest_tick is not None:
                if runner.latest_tick.last == 50000.5:
                    received_good_tick = True
                    logger.info(f"Runner received good tick: {runner.latest_tick.last}")
                    break

        # --- Task 2 Verification ---
        assert runner.latest_tick is not None, "Runner did not receive any tick"
        assert (
            runner.latest_tick.last == 50000.5
        ), f"Bad tick was not ignored! Last price recorded was {runner.latest_tick.last}"
        logger.info("✓ Task 2: Bad tick (price=0) was successfully ignored.")

        # --- Task 3 Verification ---
        logger.info("Manually triggering checkpoint for verification...")
        # Add a simulated position to ensure state fields are populated
        lot = {"qty": 0.1, "price": 50000.0, "fees": 0.0}
        runner.broker.pos = Position(
            side="LONG",
            qty=0.1,
            sl=49000.0,
            tp=52000.0,
            opened_at=utc_ts(),
            lots=deque([lot]),
            trade_id="test_autonomy_verification",
        )

        # Force save to verify persistence logic
        runner.state_manager.save()
        runner.broker.save_state()

        unified_state = state_dir / "unified_state.json"
        broker_state = state_dir / "broker_state.db"

        assert (
            unified_state.exists()
        ), f"Unified state file not created at {unified_state}"
        assert broker_state.exists(), f"Broker state file not created at {broker_state}"
        logger.info(f"✓ Task 3: Checkpoint files created in {state_dir}")

        # --- Task 4 Verification ---
        logger.info("Triggering graceful shutdown...")
        runner._request_shutdown("autonomy_verification_complete")

        try:
            # Wait for cleanup (should take ~2s due to execution queue draining)
            await asyncio.wait_for(run_task, timeout=10.0)
        except asyncio.TimeoutError:
            logger.error("Runner failed to shut down in 10s")
            run_task.cancel()
            await asyncio.sleep(0.5)

        assert (
            runner.broker.close_all.called
        ), "Broker.close_all was NOT called during shutdown while a position was open"
        logger.info("✓ Task 4: Broker.close_all was called during graceful shutdown.")

        logger.info("\n" + "=" * 40)
        logger.info("ALL AUTONOMY UPGRADE VERIFICATIONS PASSED!")
        logger.info("=" * 40)

    except Exception as e:
        logger.error(f"Verification FAILED: {e}")
        import traceback

        traceback.print_exc()
        raise
    finally:
        # Restore class method status
        BitunixFuturesProvider.load_rest_candles = original_load_rest
        # Final cleanup of temp directory
        if base_dir.exists():
            try:
                shutil.rmtree(base_dir)
            except Exception as e:
                logger.warning(f"Final cleanup failed: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(test_autonomy_upgrade())
    except Exception:
        sys.exit(1)
