from __future__ import annotations

import hashlib
import json
import time
import asyncio
import aiohttp
import math
import random
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, AsyncGenerator, Union
import tenacity

import httpx

# Resilience imports
from ...resilience import (
    ProviderError,
    TransientProviderError,
    RateLimitProviderError,
    AuthProviderError,
    UnknownProviderError,
    RetryPolicy,
    with_retry,
    log_event,
    log_provider_error,
)
from ...core.resilience import ErrorCircuitBreaker
from ...resilience.error_circuit_breaker import CircuitBreakerOpenError
from ...core.rate_limiter import exchange_rate_limiter
from ...core.logger import logger
from ...trading.helpers import Tick, DataEvent, Candle

# Bitunix Futures REST primary domain is documented as https://fapi.bitunix.com
# Market endpoints used:
# - GET /api/v1/futures/market/kline
# - GET /api/v1/futures/market/funding_rate
# - GET /api/v1/futures/market/tickers
# - GET /api/v1/futures/market/trading_pairs


def _now_ms() -> int:
    return int(time.time() * 1000)


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _minified_json(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def build_query_string(params: Optional[Dict[str, Any]]) -> str:
    """Sort params by ASCII key, then concat key+value with NO separators."""
    if not params:
        return ""
    items = sorted(params.items(), key=lambda kv: kv[0])
    return "".join([str(k) + str(v) for k, v in items])


def sign_rest(
    *,
    nonce: str,
    timestamp_ms: int,
    api_key: str,
    secret_key: str,
    query_params: str,
    body: str,
) -> str:
    """Bitunix REST signature: digest=sha256(nonce+timestamp+apiKey+queryParams+body); sign=sha256(digest+secretKey)."""
    digest = _sha256_hex(nonce + str(timestamp_ms) + api_key + query_params + body)
    return _sha256_hex(digest + secret_key)


def sign_ws(
    *, nonce: str, timestamp_ms: int, api_key: str, secret_key: str, params_string: str
) -> str:
    """Bitunix WS signature: digest=sha256(nonce+timestamp+apiKey+params); sign=sha256(digest+secretKey)."""
    digest = _sha256_hex(nonce + str(timestamp_ms) + api_key + params_string)
    return _sha256_hex(digest + secret_key)


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


class FatalError(Exception):
    pass


class BitunixFuturesProvider:
    """Public-market-data provider for Bitunix Futures.

    Notes:
    - This is intentionally *public only* so you can get unblocked candles immediately.
    - We include signing helpers here so adding live trading later is trivial.
    """

    BASE_URL = "https://fapi.bitunix.com"

    def __init__(
        self,
        *,
        symbol: str,
        allowed_symbols: Optional[Iterable[str]] = None,
        timeout_s: float = 20.0,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
    ):
        self.symbol = symbol
        self.allowed_symbols = set(allowed_symbols) if allowed_symbols else {symbol}
        self.timeout_s = timeout_s
        self.api_key = api_key
        self.secret_key = secret_key
        self._assert_allowed()

        # Resilience components
        self.retry_policy = RetryPolicy(max_attempts=3, base_delay=0.1)
        self.circuit_breaker = ErrorCircuitBreaker(
            failure_threshold=3, recovery_timeout=60, time_window=60
        )
        self.rate_limiter = exchange_rate_limiter

    def _assert_allowed(self) -> None:
        if self.symbol not in self.allowed_symbols:
            raise ValueError(
                f"Symbol '{self.symbol}' not allowed. Allowed: {sorted(self.allowed_symbols)}"
            )

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Make HTTP GET request with resilience patterns. Switches to signed if keys exist."""
        if self.api_key and self.secret_key:
            return self._get_signed(path, params)
        return self._call_exchange(
            "bitunix", "GET", lambda: self._raw_get(path, params)
        )

    def _raw_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Raw HTTP GET request without resilience."""
        url = self.BASE_URL + path
        headers = {"User-Agent": "btc-laptop-agents/0.1"}
        with httpx.Client(timeout=self.timeout_s, headers=headers) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            payload = r.json()
        if isinstance(payload, dict) and payload.get("code") != 0:
            raise RuntimeError(f"Bitunix API error: {payload}")
        return payload

    def _get_signed(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Make authenticated HTTP GET request with resilience patterns."""
        return self._call_exchange(
            "bitunix", "GET_SIGNED", lambda: self._raw_get_signed(path, params)
        )

    def _raw_get_signed(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Raw authenticated HTTP GET request."""
        if not self.api_key or not self.secret_key:
            raise RuntimeError("API key and secret key required for signed requests")

        uri = self.BASE_URL + path
        ts = _now_ms()
        nonce = str(int(time.time() * 1000000))  # Simple microsecond nonce

        # Prepare params for signature
        final_params = params.copy() if params else {}

        # Bitunix signature requirement:
        # digest = sha256(nonce + timestamp + apiKey + sorted_params_string + body)
        # sign = sha256(digest + secretKey)
        # NOTE: For GET requests, body is empty string

        qs = build_query_string(final_params)

        # Manually compute signature
        # digest = _sha256_hex(nonce + str(ts) + self.api_key + qs + "")
        # signature = _sha256_hex(digest + self.secret_key)

        # Use helper
        signature = sign_rest(
            nonce=nonce,
            timestamp_ms=ts,
            api_key=self.api_key,
            secret_key=self.secret_key,
            query_params=qs,
            body="",
        )

        headers = {
            "User-Agent": "btc-laptop-agents/0.1",
            "api-key": self.api_key,
            "timestamp": str(ts),
            "nonce": nonce,
            "sign": signature,
            # Content-Type optional for GET but good practice
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.timeout_s, headers=headers) as c:
            r = c.get(uri, params=final_params)
            r.raise_for_status()
            payload = r.json()

        if isinstance(payload, dict) and payload.get("code") != 0:
            raise RuntimeError(f"Bitunix Signed API error: {payload}")
        return payload

    def _post_signed(self, path: str, body: Dict[str, Any]) -> Any:
        """Make authenticated HTTP POST request with resilience patterns."""
        return self._call_exchange(
            "bitunix", "POST_SIGNED", lambda: self._raw_post_signed(path, body)
        )

    def _raw_post_signed(self, path: str, body: Dict[str, Any]) -> Any:
        """Raw authenticated HTTP POST request."""
        if not self.api_key or not self.secret_key:
            raise RuntimeError("API key and secret key required for signed requests")

        uri = self.BASE_URL + path
        ts = _now_ms()
        nonce = str(int(time.time() * 1000000))

        # Minify body for signature
        body_str = _minified_json(body)

        # Use helper (queryParams is empty for POST normally in Bitunix docs)
        signature = sign_rest(
            nonce=nonce,
            timestamp_ms=ts,
            api_key=self.api_key,
            secret_key=self.secret_key,
            query_params="",
            body=body_str,
        )

        headers = {
            "User-Agent": "btc-laptop-agents/0.1",
            "api-key": self.api_key,
            "timestamp": str(ts),
            "nonce": nonce,
            "sign": signature,
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.timeout_s, headers=headers) as c:
            r = c.post(uri, content=body_str)
            r.raise_for_status()
            payload = r.json()

        if isinstance(payload, dict) and payload.get("code") != 0:
            raise RuntimeError(f"Bitunix Signed POST error: {payload}")
        return payload

    def _call_exchange(self, exchange_name: str, operation: str, fn: Callable) -> Any:
        """Wrapper function for exchange calls with resilience patterns."""

        def execute_with_resilience():
            try:
                # Apply rate limit using shared limiter
                self.rate_limiter.wait_sync()

                # Apply retry policy
                @with_retry(self.retry_policy, operation)
                def wrapped_fn():
                    return fn()

                result = wrapped_fn()
                log_event(
                    "exchange_success",
                    {
                        "exchange": exchange_name,
                        "operation": operation,
                        "status": "success",
                    },
                )
                return result

            except httpx.TimeoutException as e:
                error: ProviderError = TransientProviderError(f"Timeout error: {e}")
                log_provider_error(exchange_name, operation, "TRANSIENT", str(e))
                raise error

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    error = RateLimitProviderError(f"Rate limit exceeded: {e}")
                    log_provider_error(exchange_name, operation, "RATE_LIMIT", str(e))
                elif e.response.status_code in [401, 403]:
                    error = AuthProviderError(f"Authentication error: {e}")
                    log_provider_error(exchange_name, operation, "AUTH", str(e))
                else:
                    error = UnknownProviderError(
                        f"HTTP error {e.response.status_code}: {e}"
                    )
                    log_provider_error(exchange_name, operation, "UNKNOWN", str(e))
                raise error

            except RuntimeError as e:
                error = UnknownProviderError(f"Runtime error: {e}")
                log_provider_error(exchange_name, operation, "UNKNOWN", str(e))
                raise error

            except Exception as e:
                error = UnknownProviderError(f"Unexpected error: {e}")
                log_provider_error(exchange_name, operation, "UNKNOWN", str(e))
                raise error

        # Apply circuit breaker
        if not self.circuit_breaker.allow_request():
            raise CircuitBreakerOpenError("Circuit breaker is open")

        try:
            result = execute_with_resilience()
            self.circuit_breaker.record_success()
            return result
        except Exception:
            self.circuit_breaker.record_failure()
            raise

    def trading_pairs(self) -> List[Dict[str, Any]]:
        payload = self._get(
            "/api/v1/futures/market/trading_pairs", params={"symbols": self.symbol}
        )
        return payload.get("data") or []

    @staticmethod
    def load_mock_candles(n: int = 200) -> List[Candle]:
        """Generate fake market data for testing."""
        candles: List[Candle] = []
        price = 100_000.0
        random.seed(42)

        for i in range(n):
            price += 10.0 + (random.random() - 0.5) * 400.0
            range_size = 300.0 + random.random() * 200.0
            o = price - (random.random() - 0.5) * range_size * 0.5
            c = price + (random.random() - 0.5) * range_size * 0.5
            h = max(o, c) + random.random() * range_size * 0.4
            low_val = min(o, c) - random.random() * range_size * 0.4

            ts_obj = datetime.now(timezone.utc) - timedelta(minutes=(n - i))
            candles.append(
                Candle(
                    ts=ts_obj.isoformat(),
                    open=o,
                    high=h,
                    low=low_val,
                    close=c,
                    volume=1.0,
                )
            )
        return candles

    @staticmethod
    def wait_rate_limit(retry_state: tenacity.RetryCallState) -> float:
        """Capture 429 specifically and wait longer."""
        if retry_state.outcome and isinstance(
            retry_state.outcome.exception(), RateLimitProviderError
        ):
            return 60.0
        return tenacity.wait_exponential(min=2, max=10)(retry_state)

    @classmethod
    @tenacity.retry(
        stop=tenacity.stop_after_attempt(5),
        wait=wait_rate_limit,
        retry=tenacity.retry_if_exception_type(Exception),
    )
    def load_rest_candles(cls, symbol: str, interval: str, limit: int) -> List[Candle]:
        """Fetch candles from Bitunix API with retries and WS-latest merge."""
        api_key = os.getenv("BITUNIX_API_KEY")
        secret_key = os.getenv("BITUNIX_API_SECRET") or os.getenv("BITUNIX_SECRET_KEY")

        provider = cls(symbol=symbol, api_key=api_key, secret_key=secret_key)
        out = provider.klines_paged(interval=interval, total=int(limit))

        # Merge with WS if possible (singleton client lookup)
        try:
            client = get_ws_client(symbol)
            latest = client.get_latest_candle()
            if latest:
                if not out:
                    out = [latest]
                else:
                    last_ts = out[-1].ts
                    if latest.ts > last_ts:
                        out.append(latest)
                    elif latest.ts == last_ts:
                        out[-1] = latest
        except Exception:
            pass

        return out

    @classmethod
    def get_candles_for_mode(
        cls,
        source: str,
        symbol: str,
        interval: str,
        mode: str,
        limit: int = 200,
        validate_train: int = 600,
        validate_test: int = 200,
        validate_splits: int = 5,
        **kwargs,
    ) -> List[Candle]:
        """Entry point for many orchestration flows to get candle history."""
        if source == "mock":
            if mode == "validate":
                return cls.load_mock_candles(validate_train + validate_test)
            return cls.load_mock_candles(limit)

        # For Bitunix live/rest
        provider = cls(symbol=symbol)
        if mode == "validate":
            total = validate_train + validate_test
            # Bitunix public REST max is 200, so we use klines_paged
            return provider.klines_paged(interval=interval, total=total)
        return provider.klines(interval=interval, limit=limit)

    def fetch_instrument_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Fetch precision and size limits for the symbol."""
        pairs = self.trading_pairs()
        sym = symbol or self.symbol
        for p in pairs:
            if p.get("symbol") == sym or p.get("symbolName") == sym:
                return {
                    "tickSize": float(p.get("tickSize", 0.01)),
                    "lotSize": float(p.get("lotSize", 0.001)),
                    "minQty": float(p.get("minQty", 0.001)),
                    "maxQty": float(p.get("maxQty", 100.0)),
                }
        # Fallback defaults
        return {"tickSize": 0.01, "lotSize": 0.001, "minQty": 0.001, "maxQty": 1000.0}

    def tickers(self) -> List[Dict[str, Any]]:
        payload = self._get(
            "/api/v1/futures/market/tickers", params={"symbols": self.symbol}
        )
        return payload.get("data") or []

    def funding_rate(self) -> Optional[float]:
        payload = self._get(
            "/api/v1/futures/market/funding_rate", params={"symbol": self.symbol}
        )
        data = payload.get("data")
        if not data:
            return None

        item = (
            data[0]
            if isinstance(data, list) and data
            else data
            if isinstance(data, dict)
            else {}
        )
        fr = item.get("fundingRate")

        try:
            return float(fr) if fr is not None else None
        except Exception:
            return None

    def klines(
        self,
        *,
        interval: str,
        limit: int = 200,
        start_ms: Optional[int] = None,
        end_ms: Optional[int] = None,
    ) -> List[Candle]:
        # docs: limit default 100 max 200
        limit = max(1, min(int(limit), 200))
        params: Dict[str, Any] = {
            "symbol": self.symbol,
            "interval": interval,
            "limit": limit,
        }
        if start_ms is not None:
            params["startTime"] = int(start_ms)
        if end_ms is not None:
            params["endTime"] = int(end_ms)

        payload = self._get("/api/v1/futures/market/kline", params=params)
        out: List[Candle] = []
        for row in payload.get("data") or []:
            # docs response: open/high/low/close/time
            ts_ms = int(row.get("time"))
            # Convert to ISO string for compatibility with core Candle
            ts_iso = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()
            out.append(
                Candle(
                    ts=ts_iso,
                    open=float(row.get("open")),
                    high=float(row.get("high")),
                    low=float(row.get("low")),
                    close=float(row.get("close")),
                    volume=(
                        float(row.get("baseVol"))
                        if row.get("baseVol") is not None
                        else 0.0
                    ),
                )
            )
        return out

    def klines_paged(
        self, *, interval: str, total: int, end_ms: Optional[int] = None
    ) -> List[Candle]:
        """Fetch up to 'total' most recent candles by paging backward using endTime.
        Uses public REST with max 200 per request.
        """
        remaining = int(total)
        cursor_end = end_ms
        all_rows: List[Candle] = []

        while remaining > 0:
            batch = min(200, remaining)
            rows = self.klines(interval=interval, limit=batch, end_ms=cursor_end)
            if not rows:
                break
            # API returns ascending by time in example; we handle either.
            rows_sorted = sorted(rows, key=lambda c: c.ts)
            all_rows = rows_sorted + all_rows
            remaining -= len(rows_sorted)
            # move cursor to just before earliest candle
            earliest = rows_sorted[0].ts
            cursor_end = int(datetime.fromisoformat(earliest).timestamp() * 1000) - 1
            if len(rows_sorted) < batch:
                break

        # return chronological, trimmed to total
        all_rows = sorted(all_rows, key=lambda c: c.ts)
        if len(all_rows) > total:
            all_rows = all_rows[-total:]
        return all_rows

    def snapshot_derivatives(self) -> Dict[str, Any]:
        """Return what the rest of your stack expects (funding + OI if available).

        Bitunix public docs expose funding rate; open interest is not documented on the public market endpoints,
        so we keep it None for now (you can add WS/extra endpoint later).
        """
        return {
            "funding_8h": self.funding_rate(),
            "open_interest": None,
            "basis": None,
            "liq_map": None,
            "errors": [],
        }

    def get_pending_positions(
        self, symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch current open positions."""
        params = {}
        if symbol:
            params["symbol"] = symbol

        payload = self._get_signed(
            "/api/v1/futures/position/get_pending_positions", params=params
        )
        return payload.get("data") or []

    def place_order(
        self,
        *,
        side: str,
        qty: float,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        trade_side: str = "OPEN",
        symbol: Optional[str] = None,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Place a futures order."""
        sym = symbol or self.symbol
        body = {
            "symbol": sym,
            "qty": str(qty),
            "side": side.upper(),
            "tradeSide": trade_side.upper(),
            "orderType": order_type.upper(),
        }
        if order_type.upper() == "LIMIT":
            if price is None:
                raise ValueError("Price is required for LIMIT orders")
            body["price"] = str(price)
            body["effect"] = "GTC"

        if tp_price is not None:
            body["tpPrice"] = str(tp_price)
            body["tpStopType"] = "MARK_PRICE"
            body["tpOrderType"] = "MARKET"

        if sl_price is not None:
            body["slPrice"] = str(sl_price)
            body["slStopType"] = "MARK_PRICE"
            body["slOrderType"] = "MARKET"

        return self._post_signed("/api/v1/futures/trade/place_order", body=body)

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Check status of an order."""
        payload = self._get_signed(
            "/api/v1/futures/trade/get_order", params={"orderId": order_id}
        )
        return payload.get("data") or {}

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch current open orders (unfilled)."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        payload = self._get_signed(
            "/api/v1/futures/trade/get_pending_orders", params=params
        )
        return payload.get("data", {}).get("orderList") or []

    def cancel_order(
        self, order_id: str, symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """Cancel an open order."""
        sym = symbol or self.symbol
        body = {"symbol": sym, "orderId": order_id}
        return self._post_signed("/api/v1/futures/trade/cancel_order", body=body)

    def cancel_all_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Cancel all open orders for a symbol."""
        sym = symbol or self.symbol
        body = {"symbol": sym}
        return self._post_signed("/api/v1/futures/trade/cancel_all_orders", body=body)

    def history(self, n: int = 200) -> List[Candle]:
        """Provides historical candles."""
        return self.klines(interval="1m", limit=n)

    async def listen(self) -> AsyncGenerator[Union[Candle, Tick, DataEvent], None]:
        """WebSocket adapter for the provider."""
        client = get_ws_client(self.symbol)
        client.start()
        last_yield_time = time.time()
        last_tick_ts: Optional[str] = None
        last_candle_ts: Optional[str] = None

        try:
            while True:
                # Check liveness (Zombie Detection)
                if not client.is_healthy():
                    self.circuit_breaker.record_failure()
                    if not self.circuit_breaker.allow_request():
                        logger.critical(
                            f"WS circuit breaker TRIPPED for {self.symbol}. Shutting down provider."
                        )
                        yield DataEvent(
                            event="CIRCUIT_TRIPPED",
                            ts=datetime.now(timezone.utc).isoformat(),
                            details={"reason": "Liveness check failed 3 times"},
                        )
                        break
                    else:
                        logger.warning(
                            f"WS unhealthy (zombie). Restarting client for {self.symbol}..."
                        )
                        client.stop()
                        await asyncio.sleep(1.0)
                        client.start()
                        client._last_pong = time.time()

                # Check Silence (Data stream stall)
                if (time.time() - last_yield_time) > 60.0:
                    logger.warning(
                        f"WS Silence detected (>60s). Restarting client for {self.symbol}..."
                    )
                    client.stop()
                    await asyncio.sleep(2.0)
                    client.start()
                    last_yield_time = time.time()

                # Check for ticks first
                t = client.get_latest_tick()
                if t:
                    if t.ts != last_tick_ts:
                        yield t
                        last_tick_ts = t.ts
                        last_yield_time = time.time()

                c = client.get_latest_candle()
                if c:
                    if c.ts != last_candle_ts:
                        yield c
                        last_candle_ts = c.ts
                        last_yield_time = time.time()

                await asyncio.sleep(0.05)
        finally:
            logger.info(
                f"WS: Provider listener for {self.symbol} stopped. Stopping client."
            )
            client.stop()
