"""Tests for the API budget / rate-limit manager."""

from __future__ import annotations

import time

from laptop_agents.alerts.budget import BudgetManager


class TestBudgetManager:
    """Budget manager rate limiting tests."""

    def test_can_call_initially(self) -> None:
        """Fresh budget should allow calls."""
        bm = BudgetManager()
        assert bm.can_call("binance") is True

    def test_budget_exhaustion(self) -> None:
        """After max calls, should deny further calls."""
        bm = BudgetManager(limits={"test": (3, 60.0)})
        for _ in range(3):
            assert bm.can_call("test") is True
            bm.record_call("test")
        assert bm.can_call("test") is False

    def test_budget_recovery(self) -> None:
        """After window expires, budget should recover."""
        bm = BudgetManager(limits={"test": (2, 0.5)})  # 0.5s window
        bm.record_call("test")
        bm.record_call("test")
        assert bm.can_call("test") is False

        time.sleep(0.6)  # Wait for window to expire
        assert bm.can_call("test") is True

    def test_remaining_count(self) -> None:
        """remaining() should track correctly."""
        bm = BudgetManager(limits={"test": (5, 60.0)})
        assert bm.remaining("test") == 5
        bm.record_call("test")
        assert bm.remaining("test") == 4

    def test_unknown_source_allowed(self) -> None:
        """Unknown sources should be allowed by default."""
        bm = BudgetManager()
        assert bm.can_call("unknown_source") is True

    def test_status_report(self) -> None:
        """status() should return all sources."""
        bm = BudgetManager()
        st = bm.status()
        assert "binance" in st
        assert "remaining" in st["binance"]
        assert "max" in st["binance"]

    def test_remaining_unknown(self) -> None:
        """Unknown source remaining should return 999."""
        bm = BudgetManager()
        assert bm.remaining("nonexistent") == 999
