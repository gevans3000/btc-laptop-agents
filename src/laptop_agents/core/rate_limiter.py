import asyncio
import time
import threading
from laptop_agents.core.logger import logger


class RateLimiter:
    """
    A shared rate limiter that supports both sync and async waiting.
    Ensures that total requests per second across all users of the instance
    do not exceed the limit.
    """
    def __init__(self, rps: float = 5.0, name: str = "Default"):
        self.rps = rps
        self.min_interval = 1.0 / rps
        self.last_call = 0.0
        self._lock = threading.Lock()
        self.name = name

    def _reserve_slot(self) -> float:
        """Reserve a slot and return the delay needed."""
        with self._lock:
            now = time.time()
            # If last_call is in the future, it means other tasks reserved slots already
            # If last_call is in the past, we start from 'now'
            start_point = max(now, self.last_call)
            self.last_call = start_point + self.min_interval
            
            # The delay is the time from now until the start of our reserved slot
            return start_point - now

    async def wait(self):
        """Async wait - use this in the main event loop."""
        delay = self._reserve_slot()
        if delay > 0:
            if delay > 0.001: # Avoid microscopic sleeps
                logger.debug(f"RateLimiter[{self.name}]: Async Throttling for {delay:.3f}s")
                await asyncio.sleep(delay)

    def wait_sync(self):
        """Sync wait - use this in background threads or synchronous code."""
        delay = self._reserve_slot()
        if delay > 0:
            if delay > 0.001:
                logger.debug(f"RateLimiter[{self.name}]: Sync Throttling for {delay:.3f}s")
                time.sleep(delay)

# Singleton/Shared instance for Bitunix
# Using 5.0 RPS (200ms between calls) as a safe baseline for shared REST/WS
exchange_rate_limiter = RateLimiter(rps=5.0, name="BitunixShared")
