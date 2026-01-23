import asyncio
import time
import os
import shutil
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

# Add src to path if needed, but assuming it's installed or in PYTHONPATH
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from laptop_agents.session.async_session import AsyncRunner
from laptop_agents.trading.helpers import Tick
from laptop_agents.core.logger import logger
from laptop_agents.paper.broker import Position


async def test_autonomy_upgrade():
    logger.info("Starting Autonomy Upgrade Verification...")

    # Setup
    symbol = "BTCUSDT"
    interval = "1m"
    base_dir = Path("tests/temp_autonomy_test")
    if base_dir.exists():
        shutil.rmtree(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    state_dir = base_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)

    # Mock Provider
    mock_provider = MagicMock()

    # Ticks for Task 2 test
    bad_tick = Tick(
        symbol=symbol, bid=0, ask=0, last=0, ts=str(int(time.time() * 1000))
    )
    good_tick = Tick(
        symbol=symbol,
        bid=50000,
        ask=50001,
        last=50000.5,
        ts=str(int(time.time() * 1000)),
    )

    # Use a side effect to yield items
    async def mock_listen():
        yield bad_tick
        logger.info("Sent bad tick (price=0)")
        yield good_tick
        logger.info("Sent good tick (price=50000.5)")
        # Just stay open until cancelled
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    mock_provider.listen = mock_listen
    # Mock other provider methods
    mock_provider.fetch_and_inject_gap = AsyncMock()

    runner = AsyncRunner(
        symbol=symbol,
        interval=interval,
        starting_balance=10000.0,
        provider=mock_provider,
        state_dir=state_dir,
    )

    # Task 4 Check: Mock close_all to verify it's called
    runner.broker.close_all = MagicMock(wraps=runner.broker.close_all)

    # Run the runner in the background
    # We use a 1 minute duration but we will kill it early
    run_task = asyncio.create_task(runner.run(duration_min=1))

    logger.info("Waiting for data processing...")
    await asyncio.sleep(2)

    # --- Task 2 Verification ---
    # latest_tick should be the good one because the bad one was skipped
    assert runner.latest_tick is not None, "Runner did not receive any tick"
    assert (
        runner.latest_tick.last == 50000.5
    ), f"Bad tick was not ignored! Last price: {runner.latest_tick.last}"
    logger.info("✓ Task 2: Bad tick (price=0) was successfully ignored.")

    # --- Task 3 Verification ---
    logger.info("Manually triggering checkpoint for verification...")
    # Add a real position so state is meaningful and JSON serializable
    runner.broker.pos = Position(
        side="LONG",
        entry=50000.0,
        qty=0.1,
        sl=49000.0,
        tp=52000.0,
        opened_at=str(time.time()),
    )

    # Force save
    runner.state_manager.save()
    runner.broker.save_state()

    unified_state = state_dir / "unified_state.json"
    broker_state = state_dir / "async_broker_state.json"

    assert unified_state.exists(), "Unified state file not created"
    assert broker_state.exists(), "Broker state file not created"
    logger.info(f"✓ Task 3: Checkpoint files created in {state_dir}")

    # --- Task 4 Verification ---
    logger.info("Triggering shutdown...")
    runner.shutdown_event.set()

    try:
        await asyncio.wait_for(run_task, timeout=5.0)
    except asyncio.TimeoutError:
        logger.error("Runner failed to shut down in 5s")
        run_task.cancel()

    assert (
        runner.broker.close_all.called
    ), "Broker.close_all was NOT called during shutdown"
    logger.info("✓ Task 4: Broker.close_all was called during graceful shutdown.")

    # Final cleanup
    shutil.rmtree(base_dir)
    logger.info("\n" + "=" * 40)
    logger.info("ALL AUTONOMY UPGRADE VERIFICATIONS PASSED!")
    logger.info("=" * 40)


if __name__ == "__main__":
    try:
        asyncio.run(test_autonomy_upgrade())
    except Exception as e:
        logger.error(f"Verification FAILED: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
