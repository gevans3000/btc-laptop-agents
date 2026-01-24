from __future__ import annotations

import time
from typing import Any, Dict, Optional, Callable
import httpx

from laptop_agents.core.resilience import ErrorCircuitBreaker
from laptop_agents.core.rate_limiter import exchange_rate_limiter
from laptop_agents.resilience.retry import RetryPolicy, with_retry
from laptop_agents.resilience.errors import (
    ProviderError,
    TransientProviderError,
    RateLimitProviderError,
    AuthProviderError,
    UnknownProviderError,
)
from laptop_agents.resilience.log import log_event, log_provider_error
from laptop_agents.resilience.error_circuit_breaker import CircuitBreakerOpenError
from laptop_agents.data.providers.bitunix_signing import (
    _now_ms,
    _minified_json,
    build_query_string,
    sign_rest,
)


class BitunixClient:
    """
    Handles HTTP transport, authentication, and resilience for Bitunix API.
    Decoupled from domain logic (candles, instruments).
    """

    BASE_URL = "https://fapi.bitunix.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        timeout_s: float = 20.0,
        retry_policy: Optional[RetryPolicy] = None,
        circuit_breaker: Optional[ErrorCircuitBreaker] = None,
        rate_limiter: Optional[Any] = None,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.timeout_s = timeout_s
        self.retry_policy = retry_policy or RetryPolicy(max_attempts=3, base_delay=0.1)
        self.circuit_breaker = circuit_breaker or ErrorCircuitBreaker(
            failure_threshold=3, recovery_timeout=60, time_window=60
        )
        self.rate_limiter = rate_limiter or exchange_rate_limiter

    def get(
        self, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False
    ) -> Any:
        """Execute a GET request (signed or public)."""
        if signed:
            return self._call_resilient(
                "GET_SIGNED", lambda: self._raw_get_signed(path, params)
            )
        return self._call_resilient("GET", lambda: self._raw_get(path, params))

    def post(self, path: str, body: Dict[str, Any], signed: bool = True) -> Any:
        """Execute a POST request (default signed)."""
        # Bitunix POSTs are almost always signed
        if signed:
            return self._call_resilient(
                "POST_SIGNED", lambda: self._raw_post_signed(path, body)
            )
        # Fallback for public POST if ever needed
        return self._call_resilient("POST", lambda: self._raw_post(path, body))

    def _raw_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self.BASE_URL + path
        headers = {"User-Agent": "btc-laptop-agents/0.1"}
        with httpx.Client(timeout=self.timeout_s, headers=headers) as c:
            r = c.get(url, params=params)
            r.raise_for_status()
            payload = r.json()
        self._check_payload(payload)
        return payload

    def _raw_get_signed(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        if not self.api_key or not self.secret_key:
            raise RuntimeError("API key and secret key required for signed requests")

        uri = self.BASE_URL + path
        ts = _now_ms()
        nonce = str(int(time.time() * 1000000))
        final_params = params.copy() if params else {}
        qs = build_query_string(final_params)

        signature = sign_rest(
            nonce=nonce,
            timestamp_ms=ts,
            api_key=self.api_key,
            secret_key=self.secret_key,
            query_params=qs,
            body="",
        )

        headers = {
            "api-key": self.api_key,
            "timestamp": str(ts),
            "nonce": nonce,
            "sign": signature,
            "User-Agent": "btc-laptop-agents/0.1",
        }

        with httpx.Client(timeout=self.timeout_s, headers=headers) as c:
            r = c.get(uri, params=final_params)
            r.raise_for_status()
            payload = r.json()

        self._check_payload(payload)
        return payload

    def _raw_post(self, path: str, body: Dict[str, Any]) -> Any:
        url = self.BASE_URL + path
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "btc-laptop-agents/0.1",
        }
        with httpx.Client(timeout=self.timeout_s, headers=headers) as c:
            r = c.post(url, json=body)
            r.raise_for_status()
            payload = r.json()
        self._check_payload(payload)
        return payload

    def _raw_post_signed(self, path: str, body: Dict[str, Any]) -> Any:
        if not self.api_key or not self.secret_key:
            raise RuntimeError("API key and secret key required for signed requests")

        uri = self.BASE_URL + path
        ts = _now_ms()
        nonce = str(int(time.time() * 1000000))
        body_str = _minified_json(body)

        signature = sign_rest(
            nonce=nonce,
            timestamp_ms=ts,
            api_key=self.api_key,
            secret_key=self.secret_key,
            query_params="",
            body=body_str,
        )

        headers = {
            "api-key": self.api_key,
            "timestamp": str(ts),
            "nonce": nonce,
            "sign": signature,
            "Content-Type": "application/json",
            "User-Agent": "btc-laptop-agents/0.1",
        }

        with httpx.Client(timeout=self.timeout_s, headers=headers) as c:
            r = c.post(uri, content=body_str)
            r.raise_for_status()
            payload = r.json()

        self._check_payload(payload)
        return payload

    def _check_payload(self, payload: Any) -> None:
        if isinstance(payload, dict) and payload.get("code") != 0:
            raise RuntimeError(f"Bitunix API error: {payload}")

    def _call_resilient(self, operation: str, fn: Callable) -> Any:
        """Apply rate limiting, circuit breaker, and retry logic."""
        exchange_name = "bitunix"

        def execute():
            try:
                if self.circuit_breaker.state == "OPEN":
                    # Check if recovery timeout has passed, otherwise raise
                    # Note: ErrorCircuitBreaker logic usually handles this, but let's be safe
                    # Actually, we should call circuit_breaker.call(fn) if it supported it,
                    # but here we are wrapping the call manually.
                    # We'll just check if we can proceed.
                    pass

                self.rate_limiter.wait_sync()

                @with_retry(self.retry_policy, operation)
                def wrapped():
                    return fn()

                result = wrapped()
                # Success - record in circuit breaker if needed (reset failures)
                # Our simple CircuitBreaker might not have a success hook, but that's fine.
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
                self.circuit_breaker.record_failure()
                raise error

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    error = RateLimitProviderError(f"Rate limit exceeded: {e}")
                    log_provider_error(exchange_name, operation, "RATE_LIMIT", str(e))
                    self.circuit_breaker.record_failure()
                elif e.response.status_code in [401, 403]:
                    error = AuthProviderError(f"Authentication error: {e}")
                    log_provider_error(exchange_name, operation, "AUTH", str(e))
                    # Auth errors usually shouldn't trip circuit breaker for system health,
                    # but repeated auth errors are bad. Let's trip it.
                    self.circuit_breaker.record_failure()
                else:
                    error = UnknownProviderError(
                        f"HTTP error {e.response.status_code}: {e}"
                    )
                    log_provider_error(exchange_name, operation, "UNKNOWN", str(e))
                    self.circuit_breaker.record_failure()
                raise error

            except RuntimeError as e:
                # API logic errors (code != 0)
                error = UnknownProviderError(f"Runtime error: {e}")
                log_provider_error(exchange_name, operation, "UNKNOWN", str(e))
                self.circuit_breaker.record_failure()
                raise error

            except Exception as e:
                error = UnknownProviderError(f"Unexpected error: {e}")
                log_provider_error(exchange_name, operation, "UNKNOWN", str(e))
                self.circuit_breaker.record_failure()
                raise error

        # Check circuit breaker before execution
        if self.circuit_breaker.state == "OPEN":
            # This will check if enough time passed to try again (HALF-OPEN logic usually)
            # If our circuit breaker doesn't support that internally on access, we might need to handle it.
            # Checking `src/laptop_agents/resilience/error_circuit_breaker.py`...
            # It seems to just have state and record_failure. It might not throw automatically on access.
            # We should probably throw if open.
            if (
                time.time() - self.circuit_breaker.opened_at
                < self.circuit_breaker.recovery_timeout
            ):
                raise CircuitBreakerOpenError(
                    f"Circuit breaker OPEN for {exchange_name}"
                )
            else:
                # Recovery timeout passed, reset to CLOSED (or HALF-OPEN if we had that state)
                self.circuit_breaker.state = "CLOSED"
                self.circuit_breaker.failures = []

        return execute()
