"""Tests for the alert scoring engine."""

from __future__ import annotations

import pytest

from laptop_agents.alerts.scoring import compute_score, AlertScore, Reason
from laptop_agents.alerts.features.technicals import TechnicalFeatures
from laptop_agents.alerts.features.keywords import KeywordScanResult, KeywordHit
from laptop_agents.alerts.collectors.fear_greed import FearGreedSnapshot


class TestComputeScore:
    """Tests for deterministic scoring logic."""

    def test_neutral_baseline(self) -> None:
        """No signals should produce neutral regime ~50 confidence."""
        tech = TechnicalFeatures(price=50000.0, ema_trend="neutral")
        kw = KeywordScanResult()
        score = compute_score(tech, kw)
        assert score.regime == "neutral"
        assert 45 <= score.confidence <= 55

    def test_bullish_ema_cross(self) -> None:
        """Bullish EMA cross should push regime bullish."""
        tech = TechnicalFeatures(
            price=50000.0,
            ema_short=50500.0,
            ema_long=49000.0,
            ema_trend="bullish",
        )
        kw = KeywordScanResult()
        score = compute_score(tech, kw)
        assert score.regime == "bullish"
        assert score.confidence > 55

    def test_bearish_ema_cross(self) -> None:
        """Bearish EMA should push regime bearish."""
        tech = TechnicalFeatures(
            price=50000.0,
            ema_short=48000.0,
            ema_long=50000.0,
            ema_trend="bearish",
        )
        kw = KeywordScanResult()
        score = compute_score(tech, kw)
        assert score.regime == "bearish"
        assert score.confidence < 45

    def test_extreme_fear_contrarian(self) -> None:
        """Extreme fear should contribute bullish bias."""
        tech = TechnicalFeatures(price=50000.0, ema_trend="neutral")
        kw = KeywordScanResult()
        fg = FearGreedSnapshot(value=15, label="Extreme Fear", timestamp=0.0)
        score = compute_score(tech, kw, fg)
        assert score.confidence > 55

    def test_extreme_greed_contrarian(self) -> None:
        """Extreme greed should contribute bearish bias."""
        tech = TechnicalFeatures(price=50000.0, ema_trend="neutral")
        kw = KeywordScanResult()
        fg = FearGreedSnapshot(value=85, label="Extreme Greed", timestamp=0.0)
        score = compute_score(tech, kw, fg)
        assert score.confidence < 45

    def test_keyword_sentiment_positive(self) -> None:
        """Positive keyword sentiment should push bullish."""
        tech = TechnicalFeatures(price=50000.0, ema_trend="neutral")
        kw = KeywordScanResult(net_sentiment=1.5)
        score = compute_score(tech, kw)
        assert score.confidence > 55

    def test_keyword_sentiment_negative(self) -> None:
        """Negative keyword sentiment should push bearish."""
        tech = TechnicalFeatures(price=50000.0, ema_trend="neutral")
        kw = KeywordScanResult(net_sentiment=-1.5)
        score = compute_score(tech, kw)
        assert score.confidence < 45

    def test_trump_summary_flag(self) -> None:
        """Trump policy hits should be summarized."""
        tech = TechnicalFeatures(price=50000.0, ema_trend="neutral")
        kw = KeywordScanResult(
            trump_policy_hit=True,
            hits=[
                KeywordHit(
                    keyword="strategic reserve",
                    group="trump_policy",
                    weight=0.6,
                    headline="test",
                    source="test",
                ),
            ],
        )
        score = compute_score(tech, kw)
        assert score.trump_summary != ""
        assert "strategic reserve" in score.trump_summary

    def test_degraded_data_quality(self) -> None:
        """Unhealthy technicals should mark data quality as degraded."""
        tech = TechnicalFeatures(healthy=False)
        kw = KeywordScanResult()
        score = compute_score(tech, kw)
        assert score.data_quality in ("degraded", "minimal")
        assert "price/candles" in score.degraded_sources

    def test_confidence_clamped_0_100(self) -> None:
        """Confidence should never exceed bounds."""
        tech = TechnicalFeatures(
            price=50000.0,
            ema_short=55000.0,
            ema_long=40000.0,
            ema_trend="bullish",
            momentum_pct=20.0,
        )
        kw = KeywordScanResult(net_sentiment=5.0)
        fg = FearGreedSnapshot(value=10, label="Extreme Fear", timestamp=0.0)
        score = compute_score(tech, kw, fg)
        assert 0 <= score.confidence <= 100

    def test_reasons_ranked_by_weight(self) -> None:
        """Top reasons should be ordered by absolute weight."""
        tech = TechnicalFeatures(
            price=50000.0,
            ema_short=51000.0,
            ema_long=49000.0,
            ema_trend="bullish",
            momentum_pct=3.0,
            volatility_pct=4.0,
        )
        kw = KeywordScanResult()
        score = compute_score(tech, kw)
        # Should have multiple reasons; first should have highest |weight|
        assert len(score.reasons) >= 2
        weights = [abs(r.weight) for r in score.reasons]
        assert weights == sorted(weights, reverse=True)
