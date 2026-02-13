import asyncio
import threading
import time

from btc_alert.core.logger import logger


class RateLimiter:
    """Token bucket limiter with sync/async waits."""

    def __init__(self, sustained_rps: float = 5.0, burst: float = 10.0, name: str = "api"):
        self.sustained_rps = sustained_rps
        self.burst = burst
        self.tokens = burst
        self.last_update = time.time()
        self._lock = threading.Lock()
        self.name = name

    def _reserve_slot(self) -> float:
        with self._lock:
            now = time.time()
            effective_now = max(now, self.last_update)
            elapsed = effective_now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.sustained_rps)

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                self.last_update = effective_now if effective_now == now else self.last_update
                return 0.0

            needed = 1.0 - self.tokens
            delay = (effective_now - now) + (needed / self.sustained_rps)
            self.last_update = now + delay
            self.tokens = 0.0
            return delay

    async def wait(self) -> None:
        delay = self._reserve_slot()
        if delay > 0.001:
            logger.debug("RateLimiter[%s] sleeping %.3fs", self.name, delay)
            await asyncio.sleep(delay)

    def wait_sync(self) -> None:
        delay = self._reserve_slot()
        if delay > 0.001:
            logger.debug("RateLimiter[%s] sleeping %.3fs", self.name, delay)
            time.sleep(delay)
