from __future__ import annotations

import os
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, AsyncGenerator, Union, cast
import tenacity

# Resilience imports
from ...resilience import (
    RetryPolicy,
    RateLimitProviderError,
)
from ...core.resilience import ErrorCircuitBreaker
from ...trading.helpers import Candle, Tick, DataEvent
from .bitunix_websocket import get_ws_client
from .bitunix_client import BitunixClient
from laptop_agents.core.logger import logger


class FatalError(Exception):
    pass


class BitunixFuturesProvider:
    """Public-market-data provider for Bitunix Futures.

    Notes:
    - This is intentionally *public only* so you can get unblocked candles immediately.
    - We include signing helpers here so adding live trading later is trivial.
    """

    def __init__(
        self,
        *,
        symbol: str,
        allowed_symbols: Optional[Iterable[str]] = None,
        timeout_s: float = 20.0,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        retry_policy: Optional[RetryPolicy] = None,
        circuit_breaker: Optional[ErrorCircuitBreaker] = None,
        rate_limiter: Optional[Any] = None,
    ):
        self.symbol = symbol
        self.allowed_symbols = set(allowed_symbols) if allowed_symbols else {symbol}
        self._assert_allowed()

        self.client = BitunixClient(
            api_key=api_key,
            secret_key=secret_key,
            timeout_s=timeout_s,
            retry_policy=retry_policy,
            circuit_breaker=circuit_breaker,
            rate_limiter=rate_limiter,
        )

    def _assert_allowed(self) -> None:
        if self.symbol not in self.allowed_symbols:
            raise ValueError(
                f"Symbol '{self.symbol}' not allowed. Allowed: {sorted(self.allowed_symbols)}"
            )

    def trading_pairs(self) -> List[Dict[str, Any]]:
        payload = self.client.get(
            "/api/v1/futures/market/trading_pairs", params={"symbols": self.symbol}
        )
        return payload.get("data") or []

    def get_instrument_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
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
                    "minNotional": 5.0,  # Default as Bitunix doesn't always return this explicitly in same field
                }

        raise RuntimeError(f"Instrument info not found for symbol: {sym}")

    def fetch_instrument_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Alias for get_instrument_info."""
        return self.get_instrument_info(symbol)

    @staticmethod
    def wait_rate_limit(retry_state: tenacity.RetryCallState) -> float:
        """Capture 429 specifically and wait longer."""
        if retry_state.outcome and isinstance(
            retry_state.outcome.exception(), RateLimitProviderError
        ):
            return 60.0
        return float(tenacity.wait_exponential(min=2, max=10)(retry_state))

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
        except (ImportError, RuntimeError, AttributeError) as e:
            logger.debug(f"Could not merge with WS client: {e}")

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
            from .mock import MockProvider

            if mode == "validate":
                return MockProvider.load_mock_candles(validate_train + validate_test)
            return MockProvider.load_mock_candles(limit)

        # For Bitunix live/rest
        provider = cls(symbol=symbol)
        if mode == "validate":
            total = validate_train + validate_test
            # Bitunix public REST max is 200, so we use klines_paged
            return provider.klines_paged(interval=interval, total=total)
        return provider.klines(interval=interval, limit=limit)

    def tickers(self) -> List[Dict[str, Any]]:
        payload = self.client.get(
            "/api/v1/futures/market/tickers", params={"symbols": self.symbol}
        )
        return payload.get("data") or []

    def funding_rate(self) -> Optional[float]:
        payload = self.client.get(
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
        except (ValueError, TypeError) as e:
            logger.debug(f"Could not parse funding rate: {e}")
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

        payload = self.client.get("/api/v1/futures/market/kline", params=params)
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
        }

    def get_pending_positions(
        self, symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch current open positions (signed)."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        payload = self.client.get(
            "/api/v1/futures/position/pending_position", params=params, signed=True
        )
        return payload.get("data") or []

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch current open orders (signed)."""
        params = {}
        if symbol:
            params["symbol"] = symbol
        payload = self.client.get(
            "/api/v1/futures/trade/open_orders", params=params, signed=True
        )
        return payload.get("data") or []

    def cancel_order(
        self, order_id: str, symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """Cancel a specific order (signed)."""
        body = {"orderId": order_id}
        if symbol:
            body["symbol"] = symbol
        return cast(
            Dict[str, Any],
            self.client.post(
                "/api/v1/futures/trade/cancel_order", body=body, signed=True
            ),
        )

    def place_order(
        self,
        side: str,
        qty: float,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        trade_side: Optional[str] = None,
        sl_price: Optional[float] = None,
        tp_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Place a new order (signed)."""
        # Note: Proper mapping of side/trade_side to Bitunix API ints (1,2,3,4)
        # should happen here or in client. For now ensuring signature matches usage.
        body = {
            "symbol": self.symbol,
            "side": side,
            "qty": qty,
            "type": order_type,
        }
        if price:
            body["price"] = price
        if trade_side:
            body["trade_side"] = trade_side
        if sl_price:
            body["sl"] = sl_price
        if tp_price:
            body["tp"] = tp_price

        return cast(
            Dict[str, Any],
            self.client.post("/api/v1/futures/trade/order", body=body, signed=True),
        )

    def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        """Cancel all pending orders (signed)."""
        body = {"symbol": symbol}
        return cast(
            Dict[str, Any],
            self.client.post(
                "/api/v1/futures/trade/cancel_all", body=body, signed=True
            ),
        )

    def history(self, n: int = 200) -> List[Candle]:
        """Returns n historical candles."""
        # Note: We use 1m as the default interval for history seeding
        return self.klines_paged(interval="1m", total=n)

    async def listen(self) -> AsyncGenerator[Union[Candle, Tick, DataEvent], None]:
        """Provides a stream of market data via WebSocket."""
        ws = get_ws_client(self.symbol)
        ws.start()
        try:
            while True:
                # Yield latest tick
                tick = ws.get_latest_tick()
                if tick:
                    yield tick

                # Yield latest candle
                candle = ws.get_latest_candle()
                if candle:
                    yield candle

                await asyncio.sleep(0.1)
        finally:
            ws.stop()
