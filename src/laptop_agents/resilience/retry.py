"""Retry policy with exponential backoff."""

import time
from typing import Callable, TypeVar

T = TypeVar("T")


class RetryPolicy:
    def __init__(self, max_attempts: int = 3, base_delay: float = 0.1):
        self.max_attempts = max_attempts
        self.base_delay = base_delay


def with_retry(policy: RetryPolicy, operation_name: str) -> Callable:
    """Decorator for retrying operations with exponential backoff."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(policy.max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < policy.max_attempts - 1:
                        delay = policy.base_delay * (2**attempt)
                        time.sleep(delay)

            if last_exception is not None:
                raise last_exception
            raise RuntimeError(f"Operation {operation_name} failed without exception")

        return wrapper

    return decorator


def retry_with_backoff(max_attempts: int = 3, base_delay: float = 0.1) -> Callable:
    """Decorator for retrying with exponential backoff. Alias for with_retry with params."""
    policy = RetryPolicy(max_attempts=max_attempts, base_delay=base_delay)
    return with_retry(policy, "operation")
