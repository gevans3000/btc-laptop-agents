"""Circuit breaker pattern."""

import time
from typing import Callable, TypeVar

T = TypeVar("T")


class CircuitBreaker:
    def __init__(self, max_failures: int = 3, reset_timeout: int = 60):
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.last_failure_time: float = 0.0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def guarded_call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection."""
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = "HALF_OPEN"
            else:
                raise CircuitBreakerOpenError("Circuit breaker is open")

        try:
            result = func(*args, **kwargs)
            self._reset()
            return result
        except Exception:
            self._record_failure()
            raise

    def _record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()

        if self.failures >= self.max_failures:
            self.state = "OPEN"

    def _reset(self):
        self.failures = 0
        self.state = "CLOSED"


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
