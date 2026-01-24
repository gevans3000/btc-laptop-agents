from __future__ import annotations

import asyncio
import aiohttp
import json
import math
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from laptop_agents.core.logger import logger
from laptop_agents.trading.helpers import Candle, Tick


class BitunixWebsocketClient:
    """
    Background WebSocket client for specific symbol.
    Maintains latest candle state via wss://stream.bitunix.com
    Runs strictly as an asyncio.Task in the provided loop (no threads).
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.ws_url = "wss://stream.bitunix.com/contract/ws/v1"
        self._running = False
        self._latest_candle: Optional[Candle] = None
        self._latest_tick: Optional[Tick] = None
        self._history: List[Candle] = []
        self._main_task: Optional[asyncio.Task] = None
        self._last_pong = time.time()
        self.reconnect_delay = 1.0

    def start(self):
        """Start the WebSocket connection task on the current running loop."""
        if self._running:
            return
        self._running = True
        # We assume there is a running loop since this is called from async context
        try:
            loop = asyncio.get_running_loop()
            self._main_task = loop.create_task(self._connect_and_stream())
            logger.info(f"WS: Started async task for {self.symbol}")
        except RuntimeError:
            logger.error("WS: Requires a running asyncio loop to start.")

    def stop(self):
        """Cleanly shutdown the background task."""
        if not self._running:
            return
        self._running = False
        if self._main_task:
            self._main_task.cancel()
            self._main_task = None
        logger.info(f"WS: Stopped task for {self.symbol}")

    def get_latest_candle(self) -> Optional[Candle]:
        return self._latest_candle

    def get_latest_tick(self) -> Optional[Tick]:
        val = self._latest_tick
        self._latest_tick = None  # Consume to avoid double-yielding
        return val

    def get_candles(self) -> List[Candle]:
        """Return history + latest (merged)"""
        if not self._latest_candle:
            return list(self._history)

        if not self._history:
            return [self._latest_candle]

        last_hist = self._history[-1]
        if self._latest_candle.ts > last_hist.ts:
            return self._history + [self._latest_candle]
        elif self._latest_candle.ts == last_hist.ts:
            return self._history[:-1] + [self._latest_candle]
        else:
            return list(self._history)

    async def _connect_and_stream(self):
        while self._running:
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.ws_connect(self.ws_url, heartbeat=30) as ws:
                        logger.info(f"WS: Connected to {self.ws_url} [{self.symbol}]")
                        self.reconnect_delay = 1.0

                        channels = [
                            f"market.{self.symbol}.kline.1m",
                            f"market.{self.symbol}.ticker",
                        ]
                        for chan in channels:
                            sub_msg = {
                                "event": "sub",
                                "params": {
                                    "channel": chan,
                                    "cb_id": f"{self.symbol}_{chan}",
                                },
                            }
                            await ws.send_json(sub_msg)

                        async for msg in ws:
                            if not self._running:
                                break

                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                self._last_pong = time.time()
                                if "ping" in data:
                                    await ws.send_json({"pong": data["ping"]})
                                elif (
                                    "event" in data
                                    and data["event"] == "channel_pushed"
                                ):
                                    self._handle_push(data)
                            elif msg.type in (
                                aiohttp.WSMsgType.CLOSED,
                                aiohttp.WSMsgType.ERROR,
                            ):
                                logger.error(f"WS disconnected or error: {msg.type}")
                                break

                            if not self.is_healthy():
                                logger.warning(
                                    "WS: Connection became zombie (no data >60s). Reconnecting."
                                )
                                break
            except asyncio.CancelledError:
                logger.info(f"WS: Task cancelled for {self.symbol}")
                break
            except asyncio.TimeoutError as e:
                logger.warning(f"WS: Connection timeout: {e}")
            except Exception as e:
                if "getaddrinfo failed" in str(e):
                    logger.warning(
                        "WS: Connection failed (DNS/Network Issue). Verify internet connection."
                    )
                else:
                    logger.error(f"WS: Connection error: {e}")

            if self._running:
                wait_s = min(self.reconnect_delay, 60.0)
                jitter = random.uniform(0, 5.0)
                full_wait = wait_s + jitter
                logger.warning(f"WS: Reconnecting in {full_wait:.1f}s...")
                try:
                    await asyncio.sleep(full_wait)
                except asyncio.CancelledError:
                    break
                self.reconnect_delay *= 2.0

    def is_healthy(self) -> bool:
        return (time.time() - self._last_pong) < 60.0

    def _handle_push(self, data: Dict[str, Any]):
        try:
            d = data.get("data", {})
            kline = d.get("kline")
            ticker = d.get("ticker")

            if kline:
                try:
                    ts_val = kline.get("time", 0)
                    o = float(kline.get("open", 0))
                    h = float(kline.get("high", 0))
                    low_val = float(kline.get("low", 0))
                    c = float(kline.get("close", 0))
                    v = float(kline.get("baseVol", 0))

                    if any(
                        math.isnan(x) or math.isinf(x) or x <= 0
                        for x in [o, h, low_val, c]
                    ):
                        return

                    candle = Candle(
                        ts=datetime.fromtimestamp(
                            ts_val / 1000.0, tz=timezone.utc
                        ).isoformat(),
                        open=o,
                        high=h,
                        low=low_val,
                        close=c,
                        volume=v,
                    )
                    # No lock needed in single-threaded async
                    self._latest_candle = candle
                except (ValueError, TypeError):
                    pass

            if ticker:
                try:
                    bid = float(ticker.get("buy", 0))
                    ask = float(ticker.get("sell", 0))
                    last = float(ticker.get("last", 0))
                    ts_val = ticker.get("time", 0)

                    if any(
                        math.isnan(x) or math.isinf(x) or x <= 0
                        for x in [bid, ask, last]
                    ):
                        return

                    t = Tick(
                        symbol=self.symbol,
                        bid=bid,
                        ask=ask,
                        last=last,
                        ts=datetime.fromtimestamp(
                            ts_val / 1000.0, tz=timezone.utc
                        ).isoformat(),
                    )
                    # No lock needed
                    self._latest_tick = t
                except (ValueError, TypeError):
                    pass

        except Exception as e:
            logger.error(f"WS: Unexpected parse error: {e}")


_SINGLETON_CLIENTS: Dict[str, BitunixWebsocketClient] = {}


def get_ws_client(symbol: str) -> BitunixWebsocketClient:
    if symbol not in _SINGLETON_CLIENTS:
        client = BitunixWebsocketClient(symbol)
        _SINGLETON_CLIENTS[symbol] = client
    return _SINGLETON_CLIENTS[symbol]
