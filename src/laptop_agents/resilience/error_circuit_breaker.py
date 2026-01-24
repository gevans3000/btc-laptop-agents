import time
from typing import List
from laptop_agents.core.logger import logger


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""


class ErrorCircuitBreaker:
    """
    Circuit breaker for preventing runaway error loops.
    Trips if 'failure_threshold' failures occur within 'time_window'.
    Resets after 'recovery_timeout'.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 120.0,
        time_window: int = 60,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.time_window = time_window
        self.failures: List[float] = []
        self.state = "CLOSED"
        self.opened_at = 0.0

    def record_failure(self) -> None:
        """Record a failure event."""
        now = time.time()
        self.failures.append(now)
        self._prune_failures(now)

        if len(self.failures) >= self.failure_threshold:
            self._trip()

    def record_success(self) -> None:
        """Record a success event (potentially closing the circuit)."""
        if self.state == "HALF_OPEN":
            self._reset()

    def allow_request(self) -> bool:
        """Check if execution should proceed."""
        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            if time.time() - self.opened_at > self.recovery_timeout:
                self.state = "HALF_OPEN"
                logger.info(
                    "CircuitBreaker entering HALF_OPEN state (probing availability)"
                )
                return True
            return False

        if self.state == "HALF_OPEN":
            return True

        return True

    def _prune_failures(self, now: float) -> None:
        self.failures = [t for t in self.failures if now - t <= self.time_window]

    def _trip(self) -> None:
        if self.state != "OPEN":
            self.state = "OPEN"
            self.opened_at = time.time()
            logger.warning(
                f"CircuitBreaker TRIPPED! ({len(self.failures)} failures in {self.time_window}s). "
                f"Halting for {self.recovery_timeout}s."
            )

    def _reset(self) -> None:
        self.state = "CLOSED"
        self.failures = []
        logger.info("CircuitBreaker correctly recovered. Reset to CLOSED.")
