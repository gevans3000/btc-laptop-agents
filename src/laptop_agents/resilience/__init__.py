"""Resilience patterns for exchange API calls."""

from .errors import (
    ProviderError,
    TransientProviderError,
    RateLimitProviderError,
    AuthProviderError,
    UnknownProviderError,
)
from .retry import with_retry, retry_with_backoff
from .error_circuit_breaker import ErrorCircuitBreaker
from .log import log_event, log_provider_error

# Aliases for backward compatibility
TradingCircuitBreaker = ErrorCircuitBreaker
CircuitBreaker = ErrorCircuitBreaker
ResilientLogger = log_event

__all__ = [
    "ProviderError",
    "TransientProviderError",
    "RateLimitProviderError",
    "AuthProviderError",
    "UnknownProviderError",
    "with_retry",
    "retry_with_backoff",
    "ErrorCircuitBreaker",
    "TradingCircuitBreaker",
    "CircuitBreaker",
    "log_event",
    "log_provider_error",
    "ResilientLogger",
]
