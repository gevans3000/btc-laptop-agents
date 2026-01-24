from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, AsyncGenerator, Union
import random


from laptop_agents.trading.helpers import Tick, Candle, DataEvent
import asyncio

from laptop_agents.constants import DEFAULT_SYMBOL


@dataclass
class MockProvider:
    """Deterministic candle stream for tests/demos (no internet)."""

    def __init__(
        self, seed: int = 7, start: float = 100_000.0, interval_mins: int = 1
    ) -> None:
        self.rng = random.Random(seed)
        self.price = start
        self.interval_mins = interval_mins
        self.now = datetime.now(timezone.utc) - timedelta(minutes=interval_mins * 500)

    def next_candle(self) -> Candle:
        self.now = self.now + timedelta(minutes=self.interval_mins)

        # Create a mild trend + noise so setups actually trigger
        drift = 0.00015
        noise = self.rng.uniform(-0.0009, 0.0009)
        self.price = max(1000.0, self.price * (1.0 + drift + noise))

        o = self.price * (1.0 - self.rng.uniform(0.0002, 0.0006))
        c = self.price
        hi = max(o, c) * (1.0 + self.rng.uniform(0.0002, 0.0007))
        lo = min(o, c) * (1.0 - self.rng.uniform(0.0002, 0.0007))
        v = 1.0

        return Candle(
            ts=str(int(self.now.timestamp())),
            open=o,
            high=hi,
            low=lo,
            close=c,
            volume=v,
        )

    def history(self, n: int = 200) -> List[Candle]:
        return [self.next_candle() for _ in range(n)]

    @staticmethod
    def load_mock_candles(n: int = 200) -> List[Candle]:
        """Generate fake market data for testing."""
        candles: List[Candle] = []
        price = 100_000.0
        random.seed(42)

        for i in range(n):
            price += 10.0 + (random.random() - 0.5) * 400.0
            range_size = 300.0 + random.random() * 200.0
            o = price - (random.random() - 0.5) * range_size * 0.5
            c = price + (random.random() - 0.5) * range_size * 0.5
            h = max(o, c) + random.random() * range_size * 0.4
            low_val = min(o, c) - random.random() * range_size * 0.4

            ts_obj = datetime.now(timezone.utc) - timedelta(minutes=(n - i))
            candles.append(
                Candle(
                    ts=ts_obj.isoformat(),
                    open=o,
                    high=h,
                    low=low_val,
                    close=c,
                    volume=1.0,
                )
            )
        return candles

    def get_instrument_info(self, symbol: str) -> dict:
        return {
            "tickSize": 0.01,
            "lotSize": 0.001,
            "minQty": 0.001,
            "maxQty": 1000.0,
            "minNotional": 5.0,
        }

    async def listen(self) -> AsyncGenerator[Union[Candle, Tick, DataEvent], None]:
        """Async generator that produces ticks and candles for demo/test."""

        while True:
            # Produce a "Tick"
            self.price = self.price * (1.0 + self.rng.uniform(-0.0002, 0.0002))
            tick = Tick(
                symbol=DEFAULT_SYMBOL,
                bid=self.price * 0.9999,
                ask=self.price * 1.0001,
                last=self.price,
                ts=str(int(datetime.now(timezone.utc).timestamp() * 1000)),
            )
            yield tick

            # Occasionally produce a candle (simulated every ~5 ticks)
            if self.rng.random() > 0.8:
                c = self.next_candle()
                yield Candle(
                    ts=c.ts,
                    open=c.open,
                    high=c.high,
                    low=c.low,
                    close=c.close,
                    volume=c.volume,
                )

            await asyncio.sleep(1.0)
