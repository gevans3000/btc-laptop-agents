"""Health monitoring for exchange providers."""

from typing import Dict, Any


class ProviderHealth:
    def __init__(self):
        self.stats: Dict[str, Any] = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "current_streak": 0,
            "last_error": None,
        }

    def record_success(self):
        """Record a successful call."""
        self.stats["total_calls"] += 1
        self.stats["successful_calls"] += 1
        self.stats["current_streak"] += 1
        self.stats["last_error"] = None

    def record_failure(self, error: str):
        """Record a failed call."""
        self.stats["total_calls"] += 1
        self.stats["failed_calls"] += 1
        self.stats["current_streak"] = 0
        self.stats["last_error"] = error

    def get_health_score(self) -> float:
        """Calculate health score (0-1)."""
        if self.stats["total_calls"] == 0:
            return 1.0
        return float(self.stats["successful_calls"] / self.stats["total_calls"])

    def is_healthy(self, threshold: float = 0.9) -> bool:
        """Check if provider is healthy."""
        return self.get_health_score() >= threshold
