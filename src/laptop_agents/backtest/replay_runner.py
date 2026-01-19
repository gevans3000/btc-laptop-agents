"""
Deterministic replay runner for debugging and testing.
Replays recorded ticks/candles through the trading engine.
"""

from __future__ import annotations

import json
import asyncio
from pathlib import Path
from typing import AsyncGenerator, List, Union
from laptop_agents.trading.helpers import Candle, Tick
from laptop_agents.core.logger import logger


class ReplayProvider:
    """Replays recorded market data at realistic timestamps."""

    def __init__(self, events_file: Path, speed_multiplier: float = 1.0):
        self.events_file = Path(events_file)
        self.speed_multiplier = speed_multiplier
        self._events: List[dict] = []
        self._running = False
        self._load()

    def _load(self) -> None:
        if not self.events_file.exists():
            logger.error(f"Replay file not found: {self.events_file}")
            return

        with open(self.events_file) as f:
            for line in f:
                if line.strip():
                    try:
                        self._events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        logger.info(f"Loaded {len(self._events)} events for replay")

    async def listen(self) -> AsyncGenerator[Union[Candle, Tick], None]:
        """Yield events at recorded timestamps."""
        self._running = True
        last_ts = None
        for event in self._events:
            if not self._running:
                break

            event_type = event.get("event", "")

            # Parse timestamp and sleep to maintain timing
            ts = event.get("ts") or event.get("timestamp")
            # In replay mode, we might want to skip the sleep or controlled delay
            if ts and last_ts and self.speed_multiplier > 0:
                # Simple delay to avoid flooding, but faster than real time
                await asyncio.sleep(0.01 / self.speed_multiplier)
            last_ts = ts

            # Convert to Candle or Tick
            if "candle" in event_type.lower() or "kline" in event_type.lower():
                yield Candle(
                    ts=event.get("ts", "") or event.get("time", ""),
                    open=float(event.get("open", 0)),
                    high=float(event.get("high", 0)),
                    low=float(event.get("low", 0)),
                    close=float(event.get("close", 0)),
                    volume=float(event.get("volume", 0) or event.get("baseVol", 0)),
                )
            elif (
                "tick" in event_type.lower()
                or "heartbeat" in event_type.lower()
                or "ticker" in event_type.lower()
            ):
                # Some events might be nested in 'tick' or 'ticker' topic
                data = event.get("data", event)
                if isinstance(data, list) and len(data) > 0:
                    data = data[0]

                yield Tick(
                    symbol=event.get("symbol", "BTCUSDT"),
                    bid=float(data.get("bid", data.get("bidOnePrice", 0))),
                    ask=float(data.get("ask", data.get("askOnePrice", 0))),
                    last=float(data.get("last", data.get("lastPrice", 0))),
                    ts=str(data.get("ts", data.get("time", ""))),
                )

    def stop(self):
        self._running = False
