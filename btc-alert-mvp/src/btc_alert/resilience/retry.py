"""Retry policy with exponential backoff."""

import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class RetryPolicy:
    def __init__(self, max_attempts: int = 3, base_delay: float = 0.2) -> None:
        self.max_attempts = max_attempts
        self.base_delay = base_delay


def with_retry(policy: RetryPolicy, operation_name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None
            for attempt in range(policy.max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    last_exception = exc
                    if attempt < policy.max_attempts - 1:
                        time.sleep(policy.base_delay * (2**attempt))
            if last_exception is not None:
                raise last_exception
            raise RuntimeError(f"Operation {operation_name} failed")

        return wrapper

    return decorator
