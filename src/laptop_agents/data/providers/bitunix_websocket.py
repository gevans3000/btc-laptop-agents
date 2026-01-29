"""WebSocket client for Bitunix Futures."""

from __future__ import annotations
import asyncio
import aiohttp
import json
import time
import math
import random
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from ...core.logger import logger
from ...trading.helpers import Tick, Candle
from .ws_events import OrderEvent, PositionEvent
from .bitunix_signing import sign_ws, _now_ms


class BitunixWebsocketClient:
    """
    Background WebSocket client for specific symbol.
    Maintains latest candle state via wss://stream.bitunix.com
    Runs strictly as an asyncio.Task in the provided loop (no threads).
    """

    def __init__(
        self,
        symbol: str,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        on_order_update: Optional[Callable[[OrderEvent], None]] = None,
        on_position_update: Optional[Callable[[PositionEvent], None]] = None,
    ):
        self.symbol = symbol
        self.ws_url = "wss://stream.bitunix.com/contract/ws/v1"
        self.api_key = api_key
        self.secret_key = secret_key
        self._running = False
        self._latest_candle: Optional[Candle] = None
        self._latest_tick: Optional[Tick] = None
        self._history: List[Candle] = []
        self._main_task: Optional[asyncio.Task[Any]] = None
        self._last_pong = time.time()
        self.reconnect_delay = 1.0
        self._on_order_update = on_order_update
        self._on_position_update = on_position_update
        self._authenticated = False

    def start(self) -> None:
        """Start the WebSocket connection task on the current running loop."""
        if self._running:
            return
        self._running = True
        try:
            loop = asyncio.get_running_loop()
            self._main_task = loop.create_task(self._connect_and_stream())
            logger.info(f"WS: Started async task for {self.symbol}")
        except RuntimeError:
            logger.error("WS: Requires a running asyncio loop to start.")

    def stop(self) -> None:
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

    async def _connect_and_stream(self) -> None:
        while self._running:
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.ws_connect(self.ws_url, heartbeat=30) as ws:
                        logger.info(f"WS: Connected to {self.ws_url} [{self.symbol}]")
                        self.reconnect_delay = 1.0

                        # Authenticate if credentials provided
                        if self.api_key and self.secret_key:
                            await self._authenticate(ws)

                        # Subscribe to public channels
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

                        # Subscribe to private channels if authenticated
                        if self._authenticated:
                            private_channels = [
                                f"private.{self.symbol}.plan.order",
                                f"private.{self.symbol}.position",
                            ]
                            for chan in private_channels:
                                sub_msg = {
                                    "event": "sub",
                                    "params": {
                                        "channel": chan,
                                        "cb_id": f"{self.symbol}_{chan}",
                                    },
                                }
                                await ws.send_json(sub_msg)
                            logger.info(
                                f"WS: Subscribed to private channels for {self.symbol}"
                            )

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

                            if not self.is_healthy(30):
                                logger.warning(
                                    "WS: Connection became zombie (no data >30s). Reconnecting."
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

    def is_healthy(self, threshold_sec: int = 30) -> bool:
        """Check if connection is alive (30s zombie detection threshold)."""
        return (time.time() - self._last_pong) < threshold_sec

    async def _authenticate(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Authenticate WebSocket connection for private channels."""
        try:
            ts = _now_ms()
            nonce = str(int(time.time() * 1000000))
            params_string = ""

            signature = sign_ws(
                nonce=nonce,
                timestamp_ms=ts,
                api_key=self.api_key or "",
                secret_key=self.secret_key or "",
                params_string=params_string,
            )

            auth_msg = {
                "event": "login",
                "params": {
                    "apiKey": self.api_key,
                    "timestamp": str(ts),
                    "nonce": nonce,
                    "sign": signature,
                },
            }
            await ws.send_json(auth_msg)
            self._authenticated = True
            logger.info(f"WS: Authenticated for {self.symbol}")
        except Exception as e:
            logger.error(f"WS: Authentication failed: {e}")
            self._authenticated = False

    def _handle_push(self, data: Dict[str, Any]) -> None:
        try:
            channel = data.get("channel", "")
            d = data.get("data", {})

            # Handle private channel: Plan Order
            if "plan.order" in channel and self._on_order_update:
                try:
                    order_event = OrderEvent(
                        order_id=d.get("orderId", ""),
                        symbol=d.get("symbol", self.symbol),
                        side=d.get("side", ""),
                        order_type=d.get("orderType", ""),
                        status=d.get("status", ""),
                        qty=float(d.get("qty", 0)),
                        price=float(d.get("price")) if d.get("price") else None,
                        filled_qty=float(d.get("filledQty", 0)),
                        avg_fill_price=float(d.get("avgPrice"))
                        if d.get("avgPrice")
                        else None,
                        timestamp=datetime.fromtimestamp(
                            d.get("time", 0) / 1000.0, tz=timezone.utc
                        ).isoformat(),
                        raw=d,
                    )
                    self._on_order_update(order_event)
                    logger.debug(
                        f"WS: Order update: {order_event.status} {order_event.order_id}"
                    )
                except Exception as e:
                    logger.error(f"WS: Failed to parse order event: {e}")

            # Handle private channel: Position
            elif "position" in channel and self._on_position_update:
                try:
                    position_event = PositionEvent(
                        position_id=d.get("positionId", ""),
                        symbol=d.get("symbol", self.symbol),
                        side=d.get("side", ""),
                        qty=float(d.get("qty", 0)),
                        entry_price=float(d.get("entryPrice", 0)),
                        unrealized_pnl=float(d.get("unrealizedPnl", 0)),
                        timestamp=datetime.fromtimestamp(
                            d.get("time", 0) / 1000.0, tz=timezone.utc
                        ).isoformat(),
                        raw=d,
                    )
                    self._on_position_update(position_event)
                    logger.debug(
                        f"WS: Position update: {position_event.side} {position_event.qty}"
                    )
                except Exception as e:
                    logger.error(f"WS: Failed to parse position event: {e}")

            # Handle public channel: Kline
            kline = d.get("kline")
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
                    self._latest_candle = candle
                except (ValueError, TypeError):
                    pass

            # Handle public channel: Ticker
            ticker = d.get("ticker")
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
                    self._latest_tick = t
                except (ValueError, TypeError):
                    pass

        except Exception as e:
            logger.error(f"WS: Unexpected parse error: {e}")


_SINGLETON_CLIENTS: Dict[str, BitunixWebsocketClient] = {}


def get_ws_client(
    symbol: str,
    api_key: Optional[str] = None,
    secret_key: Optional[str] = None,
    on_order_update: Optional[Callable[[OrderEvent], None]] = None,
    on_position_update: Optional[Callable[[PositionEvent], None]] = None,
) -> BitunixWebsocketClient:
    """Get or create singleton WebSocket client for a symbol."""
    if symbol not in _SINGLETON_CLIENTS:
        client = BitunixWebsocketClient(
            symbol, api_key, secret_key, on_order_update, on_position_update
        )
        _SINGLETON_CLIENTS[symbol] = client
    else:
        # Update existing singleton if it was created without credentials/callbacks
        client = _SINGLETON_CLIENTS[symbol]
        if api_key and not client.api_key:
            client.api_key = api_key
        if secret_key and not client.secret_key:
            client.secret_key = secret_key
        if on_order_update and not client._on_order_update:
            client._on_order_update = on_order_update
        if on_position_update and not client._on_position_update:
            client._on_position_update = on_position_update
    return _SINGLETON_CLIENTS[symbol]
