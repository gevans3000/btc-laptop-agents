import asyncio
import time
import threading
from laptop_agents.core.logger import logger


class RateLimiter:
    """
    A token bucket rate limiter that supports both sync and async waiting.
    Ensures sustained RPS while allowing for bursts.
    """

    def __init__(
        self, sustained_rps: float = 20.0, burst: float = 50.0, name: str = "Default"
    ):
        self.sustained_rps = sustained_rps
        self.burst = burst
        self.tokens = burst
        self.last_update = time.time()
        self._lock = threading.Lock()
        self.name = name
        self.total_wait_seconds = 0.0

    def _reserve_slot(self) -> float:
        """Reserve a token and return the delay needed."""
        with self._lock:
            now = time.time()
            effective_now = max(now, self.last_update)

            # Refill tokens
            elapsed = effective_now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.sustained_rps)

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                self.last_update = (
                    effective_now if effective_now == now else self.last_update
                )
                return 0.0
            else:
                needed = 1.0 - self.tokens
                delay_from_now = (effective_now - now) + (needed / self.sustained_rps)
                self.last_update = now + delay_from_now
                self.tokens = 0.0
                return delay_from_now

    async def wait(self) -> None:
        """Async wait - use this in the main event loop."""
        delay = self._reserve_slot()
        if delay > 0.001:
            self.total_wait_seconds += delay
            logger.debug(f"RateLimiter[{self.name}]: Async Throttling for {delay:.3f}s")
            await asyncio.sleep(delay)

    def wait_sync(self) -> None:
        """Sync wait - use this in background threads or synchronous code."""
        delay = self._reserve_slot()
        if delay > 0.001:
            self.total_wait_seconds += delay
            logger.debug(f"RateLimiter[{self.name}]: Sync Throttling for {delay:.3f}s")
            time.sleep(delay)


# Singleton/Shared instance for Bitunix
# 20 req/s sustained, 50 req/s burst as per 10-minute autonomy plan
exchange_rate_limiter = RateLimiter(
    sustained_rps=20.0, burst=50.0, name="BitunixShared"
)
