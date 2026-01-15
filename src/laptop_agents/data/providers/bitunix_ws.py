from __future__ import annotations

import asyncio
import json
import time
import socket
from typing import AsyncGenerator, List, Optional, Union
from pydantic import BaseModel, ValidationError
import websockets
from tenacity import retry, wait_exponential, stop_after_attempt, stop_never, retry_if_exception_type

from laptop_agents.core.logger import logger
from laptop_agents.trading.helpers import Candle, Tick

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
            
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.queue: asyncio.Queue[Union[Candle, Tick]] = asyncio.Queue(maxsize=1000)
        self._running = False
        self.last_message_time: float = 0.0
        self.heartbeat_timeout_sec: float = 30.0  # Plan said 10, but let's use 30 for safety on dev machines
        self.subscriptions: set[str] = set()

    async def connect(self):
        """Establish WebSocket connection."""
        logger.info(f"Connecting to Bitunix WS: {self.URL}")
        self.ws = await websockets.connect(self.URL)
        self._running = True
        logger.info("Connected to Bitunix WS")

    async def subscribe_kline(self, interval: str = "1m"):
        """Subscribe to kline channel."""
        if not self.ws:
            raise RuntimeError("WS not connected")
            
        msg = {
            "op": "subscribe",
            "args": [f"kline.{interval}.{self.symbol}"]
        }
        await self.ws.send(json.dumps(msg))
        self.subscriptions.add(f"kline.{interval}.{self.symbol}")
        logger.info(f"Subscribed to kline.{interval}.{self.symbol}")

    async def subscribe_ticker(self):
        """Subscribe to ticker channel for real-time BBO."""
        if not self.ws:
            raise RuntimeError("WS not connected")
            
        msg = {
            "op": "subscribe",
            "args": [f"ticker.{self.symbol}"]
        }
        await self.ws.send(json.dumps(msg))
        self.subscriptions.add(f"ticker.{self.symbol}")
        logger.info(f"Subscribed to ticker.{self.symbol}")

    async def _resubscribe(self):
        """Re-send all active subscriptions."""
        if not self.ws or not self.subscriptions:
            return
        
        for sub in self.subscriptions:
            msg = {
                "op": "subscribe",
                "args": [sub]
            }
            await self.ws.send(json.dumps(msg))
            logger.info(f"Resubscribed to {sub}")

    async def _handle_messages(self):
        """Internal loop to process incoming WS messages."""
        try:
            async for message in self.ws:
                self.last_message_time = time.time()
                data = json.loads(message)
                
                # Bitunix WS typically sends data in a 'topic' and 'data' format
                topic = data.get("topic")
                payload = data.get("data")
                
                if not topic or payload is None:
                    # Could be a pong or subscription confirmation
                    if data.get("op") == "ping":
                        logger.info(f"Received WS JSON Pong: {data}")
                    elif data.get("event") == "error":
                        logger.error(f"Bitunix WS error: {data}")
                    else:
                        logger.debug(f"Received WS message (no topic): {data}")
                    continue

                if "kline" in topic:
                    # Payload is usually a list of updates or a single dict
                    items = payload if isinstance(payload, list) else [payload]
                    for item in items:
                        # Map to Candle object
                        try:
                            # Use Pydantic for validation
                            validated = self.KlineMessage(**item)
                            candle = Candle(
                                ts=validated.time,
                                open=validated.open,
                                high=validated.high,
                                low=validated.low,
                                close=validated.close,
                                volume=validated.baseVol
                            )
                            try:
                                self.queue.put_nowait(candle)
                            except asyncio.QueueFull:
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
                                self.queue.put_nowait(tick)
                            except asyncio.QueueFull:
                                pass
                        except (ValidationError, TypeError, KeyError, ValueError) as e:
                            logger.error(f"Failed to parse ticker data: {e} | Data: {item}")
        except websockets.ConnectionClosed:
            logger.warning("Bitunix WS connection closed in handler")
        except Exception as e:
            logger.error(f"Error in Bitunix WS message handler: {e}")
        finally:
            self._running = False

    async def _ping_loop(self):
        """Send required JSON pings to keep connection alive."""
        while self._running:
            try:
                if self.ws:
                    ping_msg = {
                        "op": "ping",
                        "ping": int(time.time())
                    }
                    await self.ws.send(json.dumps(ping_msg))
                    logger.info("Sent WS JSON Ping")
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
                if self.ws:
                    try:
                        await self.ws.close()
                    except Exception:
                        pass
                break

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(10),  # Max 10 reconnect attempts
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
                handler_task = asyncio.create_task(self._handle_messages())
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
                
                # If we get here, the handler or heartbeat stopped
                heartbeat_task.cancel()
                ping_task.cancel()
                await handler_task
                raise websockets.ConnectionClosed(1006, "Connection lost")
                
            except (websockets.ConnectionClosed, ConnectionError) as e:
                logger.error(f"WS Connection Error: {e}")
                raise # Trigger tenacity retry
            except Exception as e:
                logger.error(f"Unexpected error in WS listen: {e}")
                raise # Trigger tenacity retry
            finally:
                if self.ws:
                    await self.ws.close()
                    self.ws = None
