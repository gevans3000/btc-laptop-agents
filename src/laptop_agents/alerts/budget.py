"""Per-source API budget / rate-limit manager."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict

logger = logging.getLogger("btc_alerts.budget")


@dataclass
class _SourceBucket:
    """Tracks calls for a single source within a rolling window."""

    max_calls: int
    window_seconds: float
    timestamps: list[float] = field(default_factory=list)

    def _prune(self) -> None:
        cutoff = time.time() - self.window_seconds
        self.timestamps = [t for t in self.timestamps if t > cutoff]

    def can_call(self) -> bool:
        self._prune()
        return len(self.timestamps) < self.max_calls

    def record(self) -> None:
        self.timestamps.append(time.time())

    @property
    def remaining(self) -> int:
        self._prune()
        return max(0, self.max_calls - len(self.timestamps))


class BudgetManager:
    """Lightweight rolling-window rate limiter for free API sources.

    Usage::

        bm = BudgetManager()
        if bm.can_call("binance"):
            bm.record_call("binance")
            # ... make the request
    """

    # Default budgets: source_key -> (max_calls, window_seconds)
    DEFAULT_LIMITS: Dict[str, tuple[int, float]] = {
        "binance": (10, 60.0),          # 10 calls / minute
        "alternative_me": (5, 300.0),   # 5 calls / 5 minutes
        "rss": (20, 300.0),             # 20 feed fetches / 5 minutes
        "llm": (5, 300.0),              # 5 LLM calls / 5 minutes
    }

    def __init__(self, limits: Dict[str, tuple[int, float]] | None = None) -> None:
        raw = limits or self.DEFAULT_LIMITS
        self._buckets: Dict[str, _SourceBucket] = {
            k: _SourceBucket(max_calls=v[0], window_seconds=v[1])
            for k, v in raw.items()
        }

    def can_call(self, source: str) -> bool:
        """Return True if *source* has budget remaining."""
        bucket = self._buckets.get(source)
        if bucket is None:
            # Unknown source – allow but warn
            logger.debug("Unknown budget source '%s'; allowing call", source)
            return True
        return bucket.can_call()

    def record_call(self, source: str) -> None:
        """Record a successful call against *source*."""
        bucket = self._buckets.get(source)
        if bucket:
            bucket.record()

    def remaining(self, source: str) -> int:
        """Return remaining calls for *source* in current window."""
        bucket = self._buckets.get(source)
        if bucket is None:
            return 999
        return bucket.remaining

    def status(self) -> Dict[str, Dict[str, int | float]]:
        """Return budget status for all sources."""
        out: Dict[str, Dict[str, int | float]] = {}
        for k, b in self._buckets.items():
            out[k] = {
                "remaining": b.remaining,
                "max": b.max_calls,
                "window_s": b.window_seconds,
            }
        return out
