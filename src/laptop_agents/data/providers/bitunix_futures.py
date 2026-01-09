from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

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
    CircuitBreaker,
    log_event,
    log_provider_error,
)

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


def sign_rest(*, nonce: str, timestamp_ms: int, api_key: str, secret_key: str, query_params: str, body: str) -> str:
    """Bitunix REST signature: digest=sha256(nonce+timestamp+apiKey+queryParams+body); sign=sha256(digest+secretKey)."""
    digest = _sha256_hex(nonce + str(timestamp_ms) + api_key + query_params + body)
    return _sha256_hex(digest + secret_key)


def sign_ws(*, nonce: str, timestamp_ms: int, api_key: str, secret_key: str, params_string: str) -> str:
    """Bitunix WS signature: digest=sha256(nonce+timestamp+apiKey+params); sign=sha256(digest+secretKey)."""
    digest = _sha256_hex(nonce + str(timestamp_ms) + api_key + params_string)
    return _sha256_hex(digest + secret_key)


@dataclass(frozen=True)
class Candle:
    ts: str  # ISO string timestamp for compatibility
    open: float
    high: float
    low: float
    close: float
    volume: float


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
        self.circuit_breaker = CircuitBreaker(max_failures=3, reset_timeout=60)

    def _assert_allowed(self) -> None:
        if self.symbol not in self.allowed_symbols:
            raise ValueError(f"Symbol '{self.symbol}' not allowed. Allowed: {sorted(self.allowed_symbols)}")

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Make HTTP GET request with resilience patterns."""
        return self._call_exchange("bitunix", "GET", lambda: self._raw_get(path, params))
    
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
        return self._call_exchange("bitunix", "GET_SIGNED", lambda: self._raw_get_signed(path, params))

    def _raw_get_signed(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
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
            body=""
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
        return self._call_exchange("bitunix", "POST_SIGNED", lambda: self._raw_post_signed(path, body))

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
            body=body_str
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

    
    def _call_exchange(self, exchange_name: str, operation: str, fn: callable) -> Any:
        """Wrapper function for exchange calls with resilience patterns."""
        def execute_with_resilience():
            try:
                # Apply retry policy
                @with_retry(self.retry_policy, operation)
                def wrapped_fn():
                    return fn()
                
                result = wrapped_fn()
                log_event("exchange_success", {
                    "exchange": exchange_name,
                    "operation": operation,
                    "status": "success"
                })
                return result
                
            except httpx.TimeoutException as e:
                error = TransientProviderError(f"Timeout error: {e}")
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
                    error = UnknownProviderError(f"HTTP error {e.response.status_code}: {e}")
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
        return self.circuit_breaker.guarded_call(execute_with_resilience)

    def trading_pairs(self) -> List[Dict[str, Any]]:
        payload = self._get("/api/v1/futures/market/trading_pairs", params={"symbols": self.symbol})
        return payload.get("data") or []

    def tickers(self) -> List[Dict[str, Any]]:
        payload = self._get("/api/v1/futures/market/tickers", params={"symbols": self.symbol})
        return payload.get("data") or []

    def funding_rate(self) -> Optional[float]:
        payload = self._get("/api/v1/futures/market/funding_rate", params={"symbol": self.symbol})
        data = payload.get("data") or []
        if not data:
            return None
        # docs show "fundingRate" string
        fr = data[0].get("fundingRate")
        try:
            return float(fr) if fr is not None else None
        except Exception:
            return None

    def klines(self, *, interval: str, limit: int = 200, start_ms: Optional[int] = None, end_ms: Optional[int] = None) -> List[Candle]:
        # docs: limit default 100 max 200
        limit = max(1, min(int(limit), 200))
        params: Dict[str, Any] = {"symbol": self.symbol, "interval": interval, "limit": limit}
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
                    volume=float(row.get("baseVol")) if row.get("baseVol") is not None else 0.0,
                )
            )
        return out

    def klines_paged(self, *, interval: str, total: int, end_ms: Optional[int] = None) -> List[Candle]:
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

    def get_pending_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch current open positions."""
        params = {}
        if symbol:
            params["symbol"] = symbol
            
        payload = self._get_signed("/api/v1/futures/position/get_pending_positions", params=params)
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
