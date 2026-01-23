import threading
import asyncio
import json
import time
import aiohttp
import math
from typing import Optional, Dict, Any, List, AsyncGenerator, Union
from datetime import datetime, timezone
import random
from laptop_agents.core.logger import logger
from laptop_agents.trading.helpers import Candle, Tick, DataEvent
from laptop_agents.resilience.error_circuit_breaker import ErrorCircuitBreaker


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
        self._main_task: Optional[asyncio.Task] = None
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
        """Cleanly shutdown the background thread and event loop."""
        if not self._running:
            return
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._cancel_main_task)

        if self._thread:
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                logger.warning(
                    f"WS: Background thread did not stop in time for {self.symbol}"
                )
            self._thread = None
        logger.info(f"WS: Stopped background thread for {self.symbol}")

    def _cancel_main_task(self) -> None:
        if self._main_task and not self._main_task.done():
            self._main_task.cancel()
        for task in asyncio.all_tasks(self._loop):
            task.cancel()

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
        try:
            self._main_task = self._loop.create_task(self._connect_and_stream())
            self._loop.run_until_complete(self._main_task)
        except asyncio.CancelledError:
            logger.info(f"WS: Stream cancelled for {self.symbol}")
        except BaseException as e:
            logger.critical(
                f"WS: Background thread crashed for {self.symbol}: {e}", exc_info=True
            )
        finally:
            # Shield against closing a running loop or double-close
            try:
                if self._loop and not self._loop.is_closed():
                    pending = asyncio.all_tasks(self._loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        self._loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                    self._loop.close()
            except Exception:
                pass

    async def _connect_and_stream(self):
        while self._running:
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.ws_connect(self.ws_url, heartbeat=30) as ws:
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
        """Returns False if it's been >60s since the last pong or push message."""
        # Increased from 15s to 60s to allow for slow startups/congestion
        return (time.time() - self._last_pong) < 60.0

    def _handle_push(self, data: Dict[str, Any]):
        try:
            d = data.get("data", {})
            kline = d.get("kline")
            ticker = d.get("ticker")

            if kline:
                # Robust validation and conversion
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
                        logger.warning(f"WS: Invalid kline prices detected: {kline}")
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
                    with self._lock:
                        self._latest_candle = candle
                except (ValueError, TypeError) as e:
                    logger.warning(f"WS: Kline numeric conversion failed: {e}")

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
                        logger.warning(f"WS: Invalid ticker prices: {ticker}")
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
                    with self._lock:
                        self._latest_tick = t
                except (ValueError, TypeError) as e:
                    logger.warning(f"WS: Ticker numeric conversion failed: {e}")

        except Exception as e:
            logger.error(f"WS: Unexpected parse error: {e}")


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
            failure_threshold=5, recovery_timeout=120, time_window=60
        )

    async def listen(self) -> AsyncGenerator[Union[Candle, Tick, DataEvent], None]:
        self.client.start()
        last_yield_time = time.time()
        last_tick_ts: Optional[str] = None
        last_candle_ts: Optional[str] = None

        try:
            while True:
                # Check liveness (Zombie Detection)
                if not self.client.is_healthy():
                    self.circuit_breaker.record_failure()
                    if not self.circuit_breaker.allow_request():
                        logger.critical(
                            f"WS circuit breaker TRIPPED for {self.symbol}. Shutting down provider."
                        )
                        yield DataEvent(
                            event="CIRCUIT_TRIPPED",
                            ts=datetime.now(timezone.utc).isoformat(),
                            details={"reason": "Liveness check failed 5 times"},
                        )
                        break
                    else:
                        # Soft restart attempts
                        logger.warning(
                            f"WS unhealthy (zombie). Restarting client for {self.symbol}..."
                        )
                        self.client.stop()
                        await asyncio.sleep(1.0)
                        self.client.start()
                        # Reset last pong so we don't loop-restart immediately
                        self.client._last_pong = time.time()

                # Check Silence (Data stream stall)
                # If healthy but no data for 60s, something is wrong with subscription
                # Increased from 15s to 60s to avoid aggressive restarts
                if (time.time() - last_yield_time) > 60.0:
                    logger.warning(
                        f"WS Silence detected (>60s). Restarting client for {self.symbol}..."
                    )
                    self.client.stop()
                    await asyncio.sleep(2.0)
                    self.client.start()
                    last_yield_time = time.time()

                # Check for ticks first
                t = self.client.get_latest_tick()
                if t:
                    # Dedupe logic if needed, but for now we trust client clears it or we handle it
                    if t.ts != last_tick_ts:
                        yield t
                        last_tick_ts = t.ts
                        last_yield_time = time.time()

                c = self.client.get_latest_candle()
                if c:
                    if c.ts != last_candle_ts:
                        yield c
                        last_candle_ts = c.ts
                        last_yield_time = time.time()

                # Polling interval
                await asyncio.sleep(0.05)
        finally:
            logger.info(
                f"WS: Provider listener for {self.symbol} stopped. Stopping client."
            )
            self.client.stop()
