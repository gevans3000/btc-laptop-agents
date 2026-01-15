from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List
import random


@dataclass(frozen=True)
class Candle:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class MockProvider:
    """Deterministic candle stream for tests/demos (no internet)."""

    def __init__(self, seed: int = 7, start: float = 100_000.0) -> None:
        self.rng = random.Random(seed)
        self.price = start
        self.now = datetime.now(timezone.utc) - timedelta(minutes=5 * 500)

    def next_candle(self) -> Candle:
        self.now = self.now + timedelta(minutes=5)

        # Create a mild trend + noise so setups actually trigger
        drift = 0.00015
        noise = self.rng.uniform(-0.0009, 0.0009)
        self.price = max(1000.0, self.price * (1.0 + drift + noise))

        o = self.price * (1.0 - self.rng.uniform(0.0002, 0.0006))
        c = self.price
        hi = max(o, c) * (1.0 + self.rng.uniform(0.0002, 0.0007))
        lo = min(o, c) * (1.0 - self.rng.uniform(0.0002, 0.0007))
        v = 1.0

        return Candle(ts=str(int(self.now.timestamp())), open=o, high=hi, low=lo, close=c, volume=v)

    def history(self, n: int = 200) -> List[Candle]:
        return [self.next_candle() for _ in range(n)]
