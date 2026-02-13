"""Per-source API budget / rate-limit manager with persistence."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("btc_alerts.budget")


@dataclass
class _SourceBucket:
    """Tracks calls for a single source within a rolling window."""

    max_calls: int
    window_seconds: float
    timestamps: List[float] = field(default_factory=list)

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

    def __init__(
        self,
        limits: Dict[str, tuple[int, float]] | None = None,
        storage_path: Optional[str] = None,
    ) -> None:
        raw = limits or self.DEFAULT_LIMITS
        self._buckets: Dict[str, _SourceBucket] = {
            k: _SourceBucket(max_calls=v[0], window_seconds=v[1])
            for k, v in raw.items()
        }

        # Resolve storage path
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            # Fallback to .workspace/alerts_budget.json
            self.storage_path = Path(os.getcwd()) / ".workspace" / "alerts_budget.json"

        self._load()

    def _load(self) -> None:
        """Load saved timestamps from disk."""
        if not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, "r") as f:
                data = json.load(f)
            for source, ts_list in data.items():
                if source in self._buckets:
                    # Filter for validity and prune
                    self._buckets[source].timestamps = [
                        t for t in ts_list if isinstance(t, (int, float))
                    ]
                    self._buckets[source]._prune()
        except Exception as exc:
            logger.warning("Failed to load budget state from %s: %s", self.storage_path, exc)

    def _save(self) -> None:
        """Save current timestamps to disk."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {k: b.timestamps for k, b in self._buckets.items()}
            with open(self.storage_path, "w") as f:
                json.dump(data, f)
        except Exception as exc:
            logger.warning("Failed to save budget state to %s: %s", self.storage_path, exc)

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
            self._save()

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
