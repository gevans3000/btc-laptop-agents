import threading
import asyncio
import json
import time
import aiohttp
from typing import Optional, Dict, Any, List, AsyncGenerator, Union
from datetime import datetime, timezone
from laptop_agents.core.logger import logger
from laptop_agents.trading.helpers import Candle, Tick, DataEvent


class FatalError(Exception):
    pass


class BitunixWebsocketClient:
    """
    Background WebSocket client for specific symbol.
    Maintains latest candle state via wss://stream.bitunix.com
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.ws_url = "wss://stream.bitunix.com/contract/ws/v1"
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._latest_candle: Optional[Candle] = None
        self._history: List[Candle] = []
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_pong = time.time()
        self.reconnect_delay = 1.0

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_thread, daemon=True)
        self._thread.start()
        logger.info(f"WS: Started background thread for {self.symbol}")

    def stop(self):
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=1.0)
        logger.info(f"WS: Stopped background thread for {self.symbol}")

    def get_latest_candle(self) -> Optional[Candle]:
        with self._lock:
            return self._latest_candle

    def get_candles(self) -> List[Candle]:
        """Return history + latest (merged)"""
        with self._lock:
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

    def _run_thread(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_and_stream())
        self._loop.close()

    async def _connect_and_stream(self):
        ctx = aiohttp.ClientSession()
        while self._running:
            try:
                async with ctx.ws_connect(self.ws_url, heartbeat=30) as ws:
                    logger.info(f"WS: Connected to {self.ws_url} [{self.symbol}]")
                    self.reconnect_delay = 1.0

                    # Subscribe
                    sub_msg = {
                        "event": "sub",
                        "params": {
                            "channel": f"market.{self.symbol}.kline.1m",
                            "cb_id": self.symbol,
                        },
                    }
                    await ws.send_json(sub_msg)

                    async for msg in ws:
                        if not self._running:
                            break
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            if "ping" in data:
                                await ws.send_json({"pong": data["ping"]})
                            elif "event" in data and data["event"] == "channel_pushed":
                                self._handle_push(data)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error("WS type error")
                            break
            except Exception as e:
                logger.error(f"WS: Connection error: {e}")

            if self._running:
                wait_s = min(self.reconnect_delay, 60.0)
                logger.warning(f"WS: Reconnecting in {wait_s}s...")
                await asyncio.sleep(wait_s)
                self.reconnect_delay *= 2.0

        await ctx.close()

    def _handle_push(self, data: Dict[str, Any]):
        try:
            # Bitunix structure: { "data": { "kline": { ... } } }
            kline = data.get("data", {}).get("kline", {})
            if not kline:
                return

            c = Candle(
                ts=datetime.fromtimestamp(
                    kline.get("time", 0) / 1000.0, tz=timezone.utc
                ).isoformat(),
                open=float(kline.get("open", 0)),
                high=float(kline.get("high", 0)),
                low=float(kline.get("low", 0)),
                close=float(kline.get("close", 0)),
                volume=float(kline.get("baseVol", 0)),
            )

            with self._lock:
                self._latest_candle = c
        except Exception as e:
            logger.error(f"WS: Parse error: {e}")


_SINGLETON_CLIENTS: Dict[str, BitunixWebsocketClient] = {}


def get_ws_client(symbol: str) -> BitunixWebsocketClient:
    if symbol not in _SINGLETON_CLIENTS:
        client = BitunixWebsocketClient(symbol)
        client.start()
        _SINGLETON_CLIENTS[symbol] = client
    return _SINGLETON_CLIENTS[symbol]


class BitunixWSProvider:
    """
    Adapter for AsyncRunner to use BitunixWebsocketClient.
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.client = get_ws_client(symbol)

    async def listen(self) -> AsyncGenerator[Union[Candle, Tick, DataEvent], None]:
        while True:
            c = self.client.get_latest_candle()
            if c:
                yield c
            # Polling interval - in a real implementation we'd use an asyncio.Queue
            # pushed to by the thread, but this is safe enough for 1m candles
            await asyncio.sleep(0.1)
