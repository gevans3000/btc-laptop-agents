import threading
import asyncio
import json
import time
import aiohttp
from typing import Optional, Dict, Any, List, AsyncGenerator, Union
from datetime import datetime, timezone
import random
from laptop_agents.core.logger import logger
from laptop_agents.trading.helpers import Candle, Tick, DataEvent
from laptop_agents.resilience.circuit import ErrorCircuitBreaker


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
        self._latest_tick: Optional[Tick] = None
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

    def get_latest_tick(self) -> Optional[Tick]:
        with self._lock:
            val = self._latest_tick
            self._latest_tick = None  # Consume to avoid double-yielding
            return val

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

                    # Subscriptions
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

                        # Zombie Detection (Phase 3)
                        # The 'async for' can block indefinitely if the link is zombie.
                        # We use is_healthy check periodically or via timeout.
                        # However, since we are in a tight loop, we rely on the next message
                        # OR if no message arrives, we need a timeout.

                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            self._last_pong = (
                                time.time()
                            )  # Track any message as liveness
                            if "ping" in data:
                                await ws.send_json({"pong": data["ping"]})
                            elif "event" in data and data["event"] == "channel_pushed":
                                self._handle_push(data)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error("WS type error")
                            break

                        if not self.is_healthy():
                            logger.warning(
                                "WS: Connection became zombie (no data > 20s). Forcefully reconnecting."
                            )
                            break

            except Exception as e:
                if "getaddrinfo failed" in str(e):
                    logger.warning(
                        "WS: Connection failed (DNS/Network Issue). Verify internet connection to Bitunix."
                    )
                else:
                    logger.error(f"WS: Connection error: {e}")

            if self._running:
                wait_s = min(self.reconnect_delay, 60.0)
                # Phase 3: Reconnection Jitter (0-5s)
                jitter = random.uniform(0, 5.0)
                full_wait = wait_s + jitter
                # Only log reconnect attempt every ~minute or so if it keeps failing
                if wait_s >= 8.0 or self.reconnect_delay == 1.0:
                    logger.warning(
                        f"WS: Reconnecting in {full_wait:.1f}s (jittered)..."
                    )
                await asyncio.sleep(full_wait)
                self.reconnect_delay *= 2.0

        await ctx.close()

    def is_healthy(self) -> bool:
        """Returns False if it's been >20s since the last pong or push message."""
        return (time.time() - self._last_pong) < 20.0

    def _handle_push(self, data: Dict[str, Any]):
        try:
            # Bitunix structure: { "data": { "kline": { ... } } }
            d = data.get("data", {})
            kline = d.get("kline")
            ticker = d.get("ticker")

            if kline:
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

            if ticker:
                # Bitunix ticker: buy=bid, sell=ask
                t = Tick(
                    symbol=self.symbol,
                    bid=float(ticker.get("buy", 0)),
                    ask=float(ticker.get("sell", 0)),
                    last=float(ticker.get("last", 0)),
                    ts=datetime.fromtimestamp(
                        ticker.get("time", 0) / 1000.0, tz=timezone.utc
                    ).isoformat(),
                )
                with self._lock:
                    self._latest_tick = t
        except Exception as e:
            logger.error(f"WS: Parse error: {e}")


_SINGLETON_CLIENTS: Dict[str, BitunixWebsocketClient] = {}


def get_ws_client(symbol: str) -> BitunixWebsocketClient:
    if symbol not in _SINGLETON_CLIENTS:
        client = BitunixWebsocketClient(symbol)
        _SINGLETON_CLIENTS[symbol] = client
    return _SINGLETON_CLIENTS[symbol]


class BitunixWSProvider:
    """
    Adapter for AsyncRunner to use BitunixWebsocketClient.
    """

    def __init__(self, symbol: str):
        self.symbol = symbol
        self.client = get_ws_client(symbol)
        self.circuit_breaker = ErrorCircuitBreaker(
            max_errors=5, reset_window_sec=120, name=f"WSProvider_{symbol}"
        )

    async def listen(self) -> AsyncGenerator[Union[Candle, Tick, DataEvent], None]:
        self.client.start()
        while True:
            if not self.client.is_healthy():
                self.circuit_breaker.record_error("WS_LIVENESS_FAILURE")
                if self.circuit_breaker.is_tripped():
                    logger.critical(
                        f"WS circuit breaker TRIPPED for {self.symbol}. Shutting down provider."
                    )
                    yield DataEvent(
                        event="CIRCUIT_TRIPPED",
                        ts=datetime.now(timezone.utc).isoformat(),
                        details={"reason": "Liveness check failed 5 times"},
                    )
                    break
            # Check for ticks first
            t = self.client.get_latest_tick()
            if t:
                yield t

            c = self.client.get_latest_candle()
            if c:
                yield c
            # Polling interval
            await asyncio.sleep(0.05)
