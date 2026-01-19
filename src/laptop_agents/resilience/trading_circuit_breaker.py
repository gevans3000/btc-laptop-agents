"""
Trading Circuit Breaker - Equity-based safety mechanism.
Halts trading when daily drawdown exceeds threshold.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


class TradingCircuitBreaker:
    """
    Monitor equity and halt trading if drawdown exceeds threshold.

    Usage:
        breaker = TradingCircuitBreaker(max_daily_drawdown_pct=5.0)
        breaker.set_starting_equity(10000.0)

        # On each trade:
        if breaker.is_tripped():
            return  # Don't trade

        # After trade update:
        breaker.update_equity(current_equity)
    """

    def __init__(
        self,
        max_daily_drawdown_pct: float = 5.0,
        max_consecutive_losses: int = 5,
    ):
        self.max_daily_drawdown_pct = max_daily_drawdown_pct
        self.max_consecutive_losses = max_consecutive_losses

        self._starting_equity: float = 0.0
        self._peak_equity: float = 0.0
        self._current_equity: float = 0.0
        self._consecutive_losses: int = 0
        self._tripped: bool = False
        self._trip_reason: Optional[str] = None
        self._trip_time: Optional[datetime] = None
        self._date: Optional[str] = None  # For daily reset

    def set_starting_equity(self, equity: float) -> None:
        """Set the starting equity for the day."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._date != today:
            # New day - reset
            self._date = today
            self._tripped = False
            self._trip_reason = None
            self._consecutive_losses = 0

        self._starting_equity = equity
        self._peak_equity = equity
        self._current_equity = equity

    def update_equity(self, equity: float, trade_pnl: Optional[float] = None) -> None:
        """Update current equity and check thresholds."""
        self._current_equity = equity
        self._peak_equity = max(self._peak_equity, equity)

        # Track consecutive losses
        if trade_pnl is not None:
            if trade_pnl < 0:
                self._consecutive_losses += 1
            else:
                self._consecutive_losses = 0

        # Check drawdown
        if self._starting_equity > 0:
            drawdown_pct = (
                (self._starting_equity - equity) / self._starting_equity
            ) * 100
            if drawdown_pct >= self.max_daily_drawdown_pct:
                self._trip(
                    "max_daily_drawdown",
                    f"Daily drawdown {drawdown_pct:.2f}% >= {self.max_daily_drawdown_pct}%",
                )

        # Check consecutive losses
        if self._consecutive_losses >= self.max_consecutive_losses:
            self._trip(
                "consecutive_losses", f"{self._consecutive_losses} consecutive losses"
            )

    def _trip(self, reason: str, detail: str) -> None:
        """Trip the circuit breaker."""
        self._tripped = True
        self._trip_reason = f"{reason}: {detail}"
        self._trip_time = datetime.now(timezone.utc)

    def is_tripped(self) -> bool:
        """Check if circuit breaker is tripped."""
        return self._tripped

    def get_status(self) -> dict:
        """Get current status for logging/display."""
        return {
            "tripped": self._tripped,
            "reason": self._trip_reason,
            "trip_time": self._trip_time.isoformat() if self._trip_time else None,
            "starting_equity": self._starting_equity,
            "current_equity": self._current_equity,
            "peak_equity": self._peak_equity,
            "consecutive_losses": self._consecutive_losses,
            "drawdown_pct": (
                (
                    (self._starting_equity - self._current_equity)
                    / self._starting_equity
                    * 100
                )
                if self._starting_equity > 0
                else 0
            ),
        }

    def reset(self) -> None:
        """Manual reset (use with caution)."""
        self._tripped = False
        self._trip_reason = None
        self._consecutive_losses = 0

    def restore_state(self, state: dict) -> None:
        """Restore state from persisted data."""
        self._tripped = state.get("tripped", False)
        self._trip_reason = state.get("reason")
        self._consecutive_losses = state.get("consecutive_losses", 0)
        self._peak_equity = state.get("peak_equity", self._starting_equity)
        if state.get("trip_time"):
            try:
                self._trip_time = datetime.fromisoformat(state["trip_time"])
            except ValueError:
                self._trip_time = None
