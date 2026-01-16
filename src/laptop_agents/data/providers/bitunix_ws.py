from __future__ import annotations

import asyncio
import json
import time
import socket
from typing import AsyncGenerator, List, Optional, Union
from pydantic import BaseModel, ValidationError
import websockets
from tenacity import retry, wait_exponential, stop_after_attempt, stop_never, retry_if_exception_type, stop_after_delay

import os
from pathlib import Path
from laptop_agents.core.logger import logger
from laptop_agents.trading.helpers import Candle, Tick
from laptop_agents.core.rate_limiter import exchange_rate_limiter

class FatalError(Exception):
    """Exception raised for fatal exchange errors that should not be retried."""
    pass

class BitunixWSProvider:
    """
    Async WebSocket provider for Bitunix Futures market data.
    Provides real-time candles and tickers.
    """
    
    # Using the standard Bitunix Futures WS endpoint
    URL = "wss://fapi.bitunix.com/public/"
    
    class KlineMessage(BaseModel):
        time: str
        open: float
        high: float
        low: float
        close: float
        baseVol: Optional[float] = 0.0
    
    class TickerMessage(BaseModel):
        bidOnePrice: Optional[float] = 0.0
        askOnePrice: Optional[float] = 0.0
        lastPrice: float
        time: str
    
    def __init__(self, symbol: str):
        # Bitunix expects symbols like BTCUSDT
        self.symbol = symbol.replace("/", "").replace("-", "").upper()
        if "USDT" not in self.symbol and "USD" not in self.symbol:
            self.symbol += "USDT"
            
        self.ws_kline: Optional[websockets.WebSocketClientProtocol] = None
        self.ws_ticker: Optional[websockets.WebSocketClientProtocol] = None
        self.queue: asyncio.Queue[Union[Candle, Tick]] = asyncio.Queue(maxsize=500)
        self._running = False
        self.connected = False
        self.last_message_time: float = 0.0
        self.heartbeat_timeout_sec: float = 30.0  # Plan said 10, but let's use 30 for safety on dev machines
        self.subscriptions: set[str] = set()
        self.time_offset: float = 0.0  # ms
        self.last_kline_ts: Optional[int] = None
        self.interval: str = "1m"

    async def connect(self):
        """Establish WebSocket connection."""
        # Load subscriptions if empty
        if not self.subscriptions:
            try:
                sub_path = Path("paper/ws_subscriptions.json")
                if sub_path.exists():
                    with open(sub_path, "r") as f:
                        saved_subs = json.load(f)
                        self.subscriptions = set(saved_subs)
                        logger.info(f"Loaded {len(self.subscriptions)} subscriptions from cache")
            except Exception as e:
                logger.warning(f"Failed to load subscriptions from cache: {e}")

        # 2.1 NTP/Server Time Synchronization
        try:
            import httpx
            from email.utils import parsedate_to_datetime
            start = time.time()
            async with httpx.AsyncClient(timeout=5.0) as client:
                await exchange_rate_limiter.wait() # Use shared limiter
                resp = await client.get("https://fapi.bitunix.com/api/v1/futures/market/tickers?symbols=BTCUSDT")
                server_date = resp.headers.get("Date")
                if server_date:
                    dt = parsedate_to_datetime(server_date)
                    server_ts = dt.timestamp() * 1000
                    latency = (time.time() - start) * 1000 / 2
                    self.time_offset = server_ts - (time.time() * 1000) + latency
                    logger.info(f"Synchronized with Bitunix. Time offset: {self.time_offset:.2f}ms")
        except Exception as e:
            logger.warning(f"Failed to sync time via REST: {e}")

        logger.info(f"Connecting to Bitunix WS (Kline): {self.URL}")
        self.ws_kline = await websockets.connect(self.URL)
        logger.info(f"Connecting to Bitunix WS (Ticker): {self.URL}")
        self.ws_ticker = await websockets.connect(self.URL)
        self._running = True
        self.connected = True
        logger.info("Connected to Bitunix Kline & Ticker WS")

    async def subscribe_kline(self, interval: str = "1m"):
        """Subscribe to kline channel."""
        self.interval = interval
        if not self.ws_kline:
            raise RuntimeError("WS kline not connected")
            
        msg = {
            "op": "subscribe",
            "args": [f"kline.{interval}.{self.symbol}"]
        }
        await self.ws_kline.send(json.dumps(msg))
        self.subscriptions.add(f"kline.{interval}.{self.symbol}")
        # Persistence
        try:
            os.makedirs("paper", exist_ok=True)
            with open("paper/ws_subscriptions.json", "w") as f:
                json.dump(list(self.subscriptions), f)
        except Exception as e:
            logger.warning(f"Failed to persist subscriptions: {e}")
        logger.info(f"Subscribed to kline.{interval}.{self.symbol}")

    async def subscribe_ticker(self):
        """Subscribe to ticker channel for real-time BBO."""
        if not self.ws_ticker:
            raise RuntimeError("WS ticker not connected")
            
        msg = {
            "op": "subscribe",
            "args": [f"ticker.{self.symbol}"]
        }
        await self.ws_ticker.send(json.dumps(msg))
        self.subscriptions.add(f"ticker.{self.symbol}")
        # Persistence
        try:
            os.makedirs("paper", exist_ok=True)
            with open("paper/ws_subscriptions.json", "w") as f:
                json.dump(list(self.subscriptions), f)
        except Exception as e:
            logger.warning(f"Failed to persist subscriptions: {e}")
        logger.info(f"Subscribed to ticker.{self.symbol}")

    async def _resubscribe(self):
        """Re-send all active subscriptions."""
        if not self.ws_kline or not self.ws_ticker or not self.subscriptions or not self.connected:
            return
        
        for sub in self.subscriptions:
            msg = {
                "op": "subscribe",
                "args": [sub]
            }
            try:
                if "kline" in sub:
                    await self.ws_kline.send(json.dumps(msg))
                else:
                    await self.ws_ticker.send(json.dumps(msg))
                logger.info(f"Resubscribed to {sub}")
            except Exception as e:
                logger.error(f"Failed to resubscribe to {sub}: {e}")
                # We don't raise here to allow other subscriptions to try, 
                # but listen() will likely fail on the next message anyway if connection is dead.

    async def _handle_messages(self, ws, name="WS"):
        """Internal loop to process incoming WS messages."""
        try:
            async for message in ws:
                self.last_message_time = time.time()
                data = json.loads(message)
                
                # Bitunix WS typically sends data in a 'topic' and 'data' format
                topic = data.get("topic")
                payload = data.get("data")
                
                if not topic or payload is None:
                    # Could be a pong or subscription confirmation
                    if data.get("op") == "ping":
                        logger.debug(f"Received {name} JSON Pong")
                    elif data.get("event") == "error":
                        msg = data.get("msg", "").lower()
                        logger.error(f"Bitunix {name} error: {data}")
                        if any(x in msg for x in ["invalid token", "ip ban", "maintenance", "authentication failed"]):
                            raise FatalError(f"Fatal Bitunix Error: {data}")
                    else:
                        logger.debug(f"Received {name} message (no topic): {data}")
                    continue

                if "kline" in topic:
                    # Payload is usually a list of updates or a single dict
                    items = payload if isinstance(payload, list) else [payload]
                    for item in items:
                        # Map to Candle object
                        try:
                            # Use Pydantic for validation
                            validated = self.KlineMessage(**item)
                            
                            new_ts = int(validated.time)
                            interval_sec = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}.get(self.interval, 60)
                            if self.last_kline_ts and new_ts > self.last_kline_ts + interval_sec:
                                logger.warning(f"Gap detected! {new_ts - self.last_kline_ts}s missing. Fetching from REST.")
                                # Start gap fill task
                                asyncio.create_task(self.fetch_and_inject_gap(self.last_kline_ts, new_ts))
                            
                            self.last_kline_ts = new_ts
                            
                            candle = Candle(
                                ts=validated.time,
                                open=validated.open,
                                high=validated.high,
                                low=validated.low,
                                close=validated.close,
                                volume=validated.baseVol
                            )
                            try:
                                if self.queue.full():
                                    self.queue.get_nowait()
                                    logger.warning("QUEUE_OVERFLOW: Dropped oldest market data item (Candle)")
                                self.queue.put_nowait(candle)
                            except (asyncio.QueueFull, asyncio.QueueEmpty):
                                pass
                            if self.last_message_time % 60 < 2: # Reduce spam
                                logger.info(f"WS Candle Update: {candle.ts} | {candle.close}")
                        except (ValidationError, TypeError, KeyError, ValueError) as e:
                            logger.error(f"Failed to parse candle data: {e} | Data: {item}")

                elif "ticker" in topic:
                    items = payload if isinstance(payload, list) else [payload]
                    for item in items:
                        # Map to Tick object
                        try:
                            # Use Pydantic for validation
                            validated = self.TickerMessage(**item)
                            tick = Tick(
                                symbol=self.symbol,
                                bid=validated.bidOnePrice or 0.0,
                                ask=validated.askOnePrice or 0.0,
                                last=validated.lastPrice,
                                ts=validated.time
                            )
                            try:
                                if self.queue.full():
                                    self.queue.get_nowait()
                                    logger.warning("QUEUE_OVERFLOW: Dropped oldest market data item (Tick)")
                                self.queue.put_nowait(tick)
                            except (asyncio.QueueFull, asyncio.QueueEmpty):
                                pass
                        except (ValidationError, TypeError, KeyError, ValueError) as e:
                            logger.error(f"Failed to parse ticker data: {e} | Data: {item}")
        except websockets.ConnectionClosed:
            logger.warning(f"Bitunix {name} connection closed in handler")
        except FatalError:
            raise
        except Exception as e:
            logger.error(f"Error in Bitunix WS message handler ({name}): {e}")
        finally:
            self._running = False

    async def funding_rate(self) -> float:
        """Fetch current funding rate via REST."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                await exchange_rate_limiter.wait() # Use shared limiter
                resp = await client.get(f"https://fapi.bitunix.com/api/v1/futures/market/funding_rate?symbol={self.symbol}")
                data = resp.json()
                if data.get("code") == 0:
                    fr_list = data.get("data", [])
                    if fr_list:
                        return float(fr_list[0].get("fundingRate", 0.0001))
        except Exception as e:
            logger.warning(f"Failed to fetch funding rate: {e}")
        return 0.0001 # Default

    async def fetch_and_inject_gap(self, start_ts: int, end_ts: int):
        """Fetch missing data from REST and inject into queue."""
        try:
            from laptop_agents.data.loader import load_bitunix_candles
            # Fetch a few more than needed just in case
            candles = await asyncio.to_thread(load_bitunix_candles, self.symbol, self.interval, limit=10)
            injected_count = 0
            for c in candles:
                try:
                    c_ts = int(c.ts)
                    if c_ts > start_ts and c_ts < end_ts:
                        logger.info(f"Injecting missing candle: {c.ts}")
                        self.queue.put_nowait(c)
                        injected_count += 1
                except (ValueError, TypeError):
                    continue
            
            if injected_count > 0:
                logger.info(f"Gap fill: Successfully injected {injected_count} candles")
            else:
                logger.warning(f"Gap fill: Found 0 candles to inject for range {start_ts} to {end_ts}")
        except Exception as e:
            logger.error(f"Failed to fetch gap data: {e}")

    async def _ping_loop(self):
        """Send required JSON pings to keep connection alive."""
        while self._running:
            try:
                ping_msg = {
                    "op": "ping",
                    "ping": int(time.time())
                }
                if self.ws_kline:
                    await self.ws_kline.send(json.dumps(ping_msg))
                if self.ws_ticker:
                    await self.ws_ticker.send(json.dumps(ping_msg))
                logger.debug("Sent WS JSON Pings (Kline & Ticker)")
            except Exception as e:
                logger.warning(f"Failed to send WS ping: {e}")
            await asyncio.sleep(5.0)

    async def _heartbeat_check(self):
        """Monitor for stale WS connection and force reconnect if needed."""
        while self._running:
            await asyncio.sleep(2.0)
            if self.last_message_time > 0 and (time.time() - self.last_message_time > self.heartbeat_timeout_sec):
                logger.warning(f"No WS message for {self.heartbeat_timeout_sec}s, forcing reconnect")
                self._running = False
                if self.ws_kline:
                    try:
                        await self.ws_kline.close()
                    except Exception:
                        pass
                if self.ws_ticker:
                    try:
                        await self.ws_ticker.close()
                    except Exception:
                        pass
                break

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_delay(600),  # Survival for 10 minutes of outage
        retry=retry_if_exception_type((websockets.ConnectionClosed, ConnectionError, asyncio.TimeoutError, socket.gaierror)),
        before_sleep=lambda retry_state: logger.warning(
            f"Bitunix WS connection lost. Attempting reconnect in {retry_state.next_action.sleep:.1f}s..."
        )
    )
    async def listen(self) -> AsyncGenerator[Union[Candle, Tick], None]:
        """
        Primary entry point. Yields Candle or Tick objects with auto-reconnect.
        """
        while True:
            try:
                await self.connect()
                if not self.subscriptions:
                    await self.subscribe_kline()
                    await asyncio.sleep(1.0)
                    await self.subscribe_ticker()
                else:
                    await self._resubscribe()
                
                # Run tasks in the background
                self.last_message_time = time.time()  # Reset on connect
                kline_handler = asyncio.create_task(self._handle_messages(self.ws_kline, "Kline"))
                ticker_handler = asyncio.create_task(self._handle_messages(self.ws_ticker, "Ticker"))
                heartbeat_task = asyncio.create_task(self._heartbeat_check())
                ping_task = asyncio.create_task(self._ping_loop())
                
                while self._running:
                    try:
                        # Use a timeout so we can check if the handler is still running
                        item = await asyncio.wait_for(self.queue.get(), timeout=5.0)
                        yield item
                    except asyncio.TimeoutError:
                        if not self._running:
                            break
                        continue
                
                # If we get here, one of the handlers or heartbeat stopped
                heartbeat_task.cancel()
                ping_task.cancel()
                kline_handler.cancel()
                ticker_handler.cancel()
                await asyncio.gather(kline_handler, ticker_handler, return_exceptions=True)
                raise websockets.ConnectionClosed(1006, "Connection lost")
                
            except FatalError:
                # Bubble up fatal errors, don't let tenacity catch them
                raise
            except (websockets.ConnectionClosed, ConnectionError) as e:
                logger.error(f"WS Connection Error: {e}")
                raise # Trigger tenacity retry
            except Exception as e:
                logger.error(f"Unexpected error in WS listen: {e}")
                raise # Trigger tenacity retry
            finally:
                self.connected = False
                if self.ws_kline:
                    await self.ws_kline.close()
                    self.ws_kline = None
                if self.ws_ticker:
                    await self.ws_ticker.close()
                    self.ws_ticker = None
