import asyncio
import os
from contextlib import suppress
import psutil
import pytest
from laptop_agents.session.async_session import AsyncRunner
from laptop_agents.trading.helpers import Tick, Candle


class HighSpeedMockProvider:
    """Generates market data at 100x speed."""

    def __init__(self, count=1000):
        self.count = count
        self.stop = False

    def history(self, count):
        price = 100000.0
        candles = []
        for i in range(count):
            candles.append(
                Candle(
                    ts=f"2025-01-01T{i % 24:02d}:00:00Z",
                    open=price,
                    high=price + 10,
                    low=price - 10,
                    close=price,
                    volume=100.0,
                )
            )
        return candles

    async def listen(self):
        price = 100000.0
        for i in range(self.count):
            if self.stop:
                break

            # Generate a tick
            price += (hash(i) % 100 - 50) / 10.0
            yield Tick(
                symbol="BTCUSDT",
                bid=price - 1.0,
                ask=price + 1.0,
                last=price,
                ts=f"2025-01-01T{i % 24:02d}:00:00Z",
            )

            # Every 10 ticks, generate a candle
            if i % 10 == 0:
                yield Candle(
                    ts=f"2025-01-01T{i % 24:02d}:00:00Z",
                    open=price,
                    high=price + 10,
                    low=price - 10,
                    close=price,
                    volume=100.0,
                )

            # Tiny sleep to allow context switch but go fast
            await asyncio.sleep(0.001)


@pytest.mark.asyncio
async def test_memory_leak_long_run():
    """Run a high-speed session and ensure memory stable."""
    process = psutil.Process(os.getpid())
    start_mem = process.memory_info().rss / 1024 / 1024

    # Run for equivalent of >10 minutes of data in seconds
    # 10 mins * 60 secs * 10 ticks/sec = 6000 ticks
    provider = HighSpeedMockProvider(count=6000)

    runner = AsyncRunner(
        symbol="BTCUSDT",
        interval="1m",
        provider=provider,
        stale_timeout=999,  # Disable stale check for mock
    )

    # We want to run until provider exhausts or a timeout
    # We can use runner.run() but it runs by time.
    # Let's set a short real-time duration but push data fast.

    # Actually, AsyncRunner.run() waits for duration.
    # We will override the timer task or just set duration to 1 min (real time)
    # while pushing 10 mins worth of data.

    run_task = asyncio.create_task(runner.run(duration_min=1))
    try:
        await asyncio.wait_for(run_task, timeout=10.0)
    except asyncio.TimeoutError:
        runner.shutdown_event.set()
        with suppress(asyncio.TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(run_task, timeout=5.0)
    except Exception:
        runner.shutdown_event.set()
    finally:
        if not run_task.done():
            runner.shutdown_event.set()
            run_task.cancel()
            with suppress(asyncio.CancelledError):
                await run_task

    # In reality, provider finishes yielding, loop inside market_data_task finishes?
    # The AsyncRunner.market_data_task has `async for item in self.provider.listen()`.
    # When provider finishes, the loop finishes.
    # But AsyncRunner doesn't shut down when data finishes, it waits for time.
    # So we should probably cancel it manually or check state.

    end_mem = process.memory_info().rss / 1024 / 1024
    growth = end_mem - start_mem

    print(
        f"Start Mem: {start_mem:.2f}MB, End Mem: {end_mem:.2f}MB, Growth: {growth:.2f}MB"
    )

    # Assertion: clean run should not leak > 200MB
    assert growth < 200.0, f"Memory leak detected! Growth: {growth:.2f}MB"
