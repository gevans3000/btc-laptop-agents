
import time
import threading
from typing import Optional

class SimpleRateLimiter:
    """A thread-safe simple rate limiter that enforces a minimum interval between calls."""
    
    def __init__(self, requests_per_second: float):
        self.interval = 1.0 / requests_per_second
        self.last_call_time = 0.0
        self._lock = threading.Lock()
        
    def wait(self):
        """Wait if necessary to maintain the rate limit."""
        with self._lock:
            now = time.time()
            elapsed = now - self.last_call_time
            sleep_time = self.interval - elapsed
            
            if sleep_time > 0:
                time.sleep(sleep_time)
                self.last_call_time = time.time()
            else:
                self.last_call_time = now
