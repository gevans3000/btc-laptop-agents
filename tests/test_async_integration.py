import pytest
import asyncio
from laptop_agents.session.async_session import AsyncRunner
from laptop_agents.trading.helpers import Candle, Tick


class MockProvider:
    def __init__(self, symbol="BTCUSDT"):
        self.symbol = symbol
        self.connected = True

    async def listen(self):
        # Yield 5 mock ticks then 5 mock candles
        for i in range(5):
            yield Tick(
                symbol=self.symbol,
                bid=50000.0,
                ask=50001.0,
                last=50000.5,
                ts=str(1700000000 + i),
            )
            await asyncio.sleep(0.01)

        for i in range(5):
            yield Candle(
                ts=str(1700000000 + i * 60),
                open=50000.0,
                high=50100.0,
                low=49900.0,
                close=50050.0,
                volume=1.0,
            )
            await asyncio.sleep(0.01)

    async def funding_rate(self):
        return 0.0001


@pytest.mark.asyncio
async def test_async_integration():
    mock_provider = MockProvider()

    # We use a short duration
    runner = AsyncRunner(symbol="BTCUSDT", interval="1m", provider=mock_provider)

    # Run for a very short time
    # Since mock_provider.listen() will eventually finish or we can cancel it
    # We'll run it in a task and cancel after a few seconds

    run_task = asyncio.create_task(runner.run(duration_min=1))

    # Wait for some processing
    await asyncio.sleep(0.5)

    # Trigger shutdown
    runner.shutdown_event.set()

    await run_task

    assert runner.iterations >= 0
    assert runner.errors == 0
