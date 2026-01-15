from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncGenerator, List, Optional, Union
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
    
    def __init__(self, symbol: str):
        # Bitunix expects symbols like BTCUSDT
        self.symbol = symbol.replace("/", "").replace("-", "").upper()
        if "USDT" not in self.symbol and "USD" not in self.symbol:
            self.symbol += "USDT"
            
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.queue: asyncio.Queue[Union[Candle, Tick]] = asyncio.Queue()
        self._running = False

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
        logger.info(f"Subscribed to ticker.{self.symbol}")

    async def _handle_messages(self):
        """Internal loop to process incoming WS messages."""
        try:
            async for message in self.ws:
                data = json.loads(message)
                
                # Bitunix WS typically sends data in a 'topic' and 'data' format
                topic = data.get("topic")
                payload = data.get("data")
                
                if not topic or payload is None:
                    # Could be a pong or subscription confirmation
                    if data.get("event") == "error":
                        logger.error(f"Bitunix WS error: {data}")
                    continue

                if "kline" in topic:
                    # Payload is usually a list of updates or a single dict
                    items = payload if isinstance(payload, list) else [payload]
                    for item in items:
                        # Map to Candle object
                        try:
                            candle = Candle(
                                ts=str(item.get("time")),
                                open=float(item["open"]),
                                high=float(item["high"]),
                                low=float(item["low"]),
                                close=float(item["close"]),
                                volume=float(item.get("baseVol", 0))
                            )
                            await self.queue.put(candle)
                        except (KeyError, ValueError) as e:
                            logger.error(f"Failed to parse candle data: {e} | Data: {item}")

                elif "ticker" in topic:
                    items = payload if isinstance(payload, list) else [payload]
                    for item in items:
                        # Map to Tick object
                        try:
                            tick = Tick(
                                symbol=self.symbol,
                                bid=float(item.get("bidOnePrice", 0)),
                                ask=float(item.get("askOnePrice", 0)),
                                last=float(item.get("lastPrice", 0)),
                                ts=str(item.get("time"))
                            )
                            await self.queue.put(tick)
                        except (KeyError, ValueError) as e:
                            logger.error(f"Failed to parse ticker data: {e} | Data: {item}")
        except websockets.ConnectionClosed:
            logger.warning("Bitunix WS connection closed in handler")
        except Exception as e:
            logger.error(f"Error in Bitunix WS message handler: {e}")
        finally:
            self._running = False

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(10),  # Max 10 reconnect attempts
        retry=retry_if_exception_type((websockets.ConnectionClosed, ConnectionError, asyncio.TimeoutError)),
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
                await self.subscribe_kline()
                await self.subscribe_ticker()
                
                # Run the message handler in the background
                handler_task = asyncio.create_task(self._handle_messages())
                
                while self._running:
                    try:
                        # Use a timeout so we can check if the handler is still running
                        item = await asyncio.wait_for(self.queue.get(), timeout=5.0)
                        yield item
                    except asyncio.TimeoutError:
                        if not self._running:
                            break
                        continue
                
                # If we get here, the handler stopped (likely connection closed)
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
