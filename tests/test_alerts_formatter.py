"""Tests for the alert message formatter."""

from __future__ import annotations

from laptop_agents.alerts.formatter import format_alert_message
from laptop_agents.alerts.scoring import AlertScore


class TestFormatAlertMessage:
    """Alert formatting tests."""

    def test_basic_format(self) -> None:
        """Formatted message should contain required fields."""
        score = AlertScore(
            regime="bullish",
            confidence=72,
            top_reasons=["EMA cross bullish", "Momentum up 2.5%"],
        )
        msg = format_alert_message(score, price=51234.56, summary="Test summary")
        assert "$51,234.56" in msg
        assert "BULLISH" in msg
        assert "72/100" in msg
        assert "EMA cross bullish" in msg
        assert "Test summary" in msg
        assert "Next check" in msg

    def test_degraded_mode_shown(self) -> None:
        """Degraded data quality should appear in message."""
        score = AlertScore(
            regime="neutral",
            confidence=50,
            data_quality="degraded",
            degraded_sources=["price/candles"],
        )
        msg = format_alert_message(score, price=50000.0, summary="")
        assert "degraded" in msg.lower()

    def test_trump_keywords_shown(self) -> None:
        """Trump policy keywords should appear if present."""
        score = AlertScore(
            regime="bullish",
            confidence=65,
            trump_summary="strategic reserve, tariff",
        )
        msg = format_alert_message(score, price=50000.0, summary="")
        assert "strategic reserve" in msg
        assert "Policy Keywords" in msg

    def test_momentum_direction_emoji(self) -> None:
        """Positive momentum should show 📈, negative 📉."""
        score = AlertScore(regime="bullish", confidence=60)
        msg_up = format_alert_message(score, price=50000.0, summary="", momentum_pct=2.5)
        assert "📈" in msg_up

        msg_down = format_alert_message(score, price=50000.0, summary="", momentum_pct=-1.5)
        assert "📉" in msg_down

    def test_no_reasons_handled(self) -> None:
        """Message should still format cleanly with no reasons."""
        score = AlertScore(regime="neutral", confidence=50)
        msg = format_alert_message(score, price=50000.0, summary="No signal")
        assert "neutral" in msg.lower() or "NEUTRAL" in msg
