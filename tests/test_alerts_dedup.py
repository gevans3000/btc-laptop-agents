"""Tests for Telegram notifier dedup and cooldown logic."""

from __future__ import annotations

import time

import pytest

from laptop_agents.alerts.telegram_notifier import TelegramNotifier


class TestDedup:
    """Dedup and cooldown tests (no actual Telegram calls)."""

    def _notifier(self, cooldown: float = 2.0) -> TelegramNotifier:
        """Create an unconfigured notifier (no token → prints to console)."""
        return TelegramNotifier(
            bot_token="",
            chat_id="",
            cooldown_seconds=cooldown,
        )

    def test_duplicate_detection(self) -> None:
        """Same message hash within cooldown should be detected as duplicate."""
        n = self._notifier(cooldown=60.0)
        msg = "BTC alert: $50,000 bullish 75% confidence"
        # Simulate a sent message by recording the hash
        h = n._message_hash(msg)
        n._sent_hashes[h] = time.time()
        assert n._is_duplicate(msg) is True

    def test_different_message_not_duplicate(self) -> None:
        """Different messages should not be flagged as duplicates."""
        n = self._notifier(cooldown=60.0)
        msg1 = "BTC alert: $50,000 bullish 75% confidence"
        msg2 = "BTC alert: $48,000 bearish 30% confidence"
        h = n._message_hash(msg1)
        n._sent_hashes[h] = time.time()
        assert n._is_duplicate(msg2) is False

    def test_expired_duplicate_allowed(self) -> None:
        """Messages older than cooldown should not be flagged."""
        n = self._notifier(cooldown=1.0)
        msg = "BTC alert: $50,000 bullish 75% confidence"
        h = n._message_hash(msg)
        n._sent_hashes[h] = time.time() - 5.0  # 5 seconds ago, cooldown is 1s
        assert n._is_duplicate(msg) is False

    def test_cooldown_active(self) -> None:
        """Global cooldown should block sends."""
        n = self._notifier(cooldown=60.0)
        n._last_send_time = time.time()
        assert n._in_cooldown() is True

    def test_cooldown_expired(self) -> None:
        """Expired cooldown should allow sends."""
        n = self._notifier(cooldown=1.0)
        n._last_send_time = time.time() - 5.0
        assert n._in_cooldown() is False

    def test_unconfigured_falls_back_to_console(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Unconfigured notifier should print to console and return False."""
        n = self._notifier()
        result = n.send("Test alert message", force=True)
        assert result is False
        captured = capsys.readouterr()
        assert "ALERT" in captured.out

    def test_configured_property(self) -> None:
        """configured should be True only when both token and chat_id are set."""
        n1 = TelegramNotifier(bot_token="", chat_id="")
        assert n1.configured is False

        n2 = TelegramNotifier(bot_token="tok", chat_id="")
        assert n2.configured is False

        n3 = TelegramNotifier(bot_token="tok", chat_id="123")
        assert n3.configured is True
