"""Resilience patterns for exchange API calls."""

from .errors import (
    ProviderError,
    TransientProviderError,
    RateLimitProviderError,
    AuthProviderError,
    UnknownProviderError,
)
from .retry import RetryPolicy, with_retry
from .circuit import CircuitBreaker, CircuitBreakerOpenError
from .log import log_event, log_provider_error

__all__ = [
    "ProviderError",
    "TransientProviderError", 
    "RateLimitProviderError",
    "AuthProviderError",
    "UnknownProviderError",
    "RetryPolicy",
    "with_retry",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "guarded_call",
    "log_event",
    "log_provider_error",
]
