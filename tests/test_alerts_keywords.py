"""Tests for the keyword scanner."""

from __future__ import annotations

from laptop_agents.alerts.features.keywords import scan_keywords, KeywordScanResult
from laptop_agents.alerts.collectors.news import Headline


class TestKeywordScanner:
    """Keyword scan tests."""

    def test_empty_headlines(self) -> None:
        """No headlines should produce empty result."""
        result = scan_keywords([])
        assert result.hits == []
        assert result.net_sentiment == 0.0

    def test_trump_keyword_detection(self) -> None:
        """Trump policy keywords should be detected and flagged."""
        headlines = [
            Headline(title="Trump announces strategic reserve for Bitcoin", source="test"),
        ]
        result = scan_keywords(headlines)
        assert result.trump_policy_hit is True
        assert any(h.keyword == "strategic reserve" for h in result.hits)

    def test_macro_keyword_detection(self) -> None:
        """Macro keywords should be detected."""
        headlines = [
            Headline(title="Fed announces surprise rate cut", source="test"),
        ]
        result = scan_keywords(headlines)
        assert any(h.keyword == "rate cut" for h in result.hits)
        assert result.net_sentiment > 0  # rate cut is bullish

    def test_negative_sentiment(self) -> None:
        """Bearish keywords should produce negative net sentiment."""
        headlines = [
            Headline(title="Major exchange suffers hack and exploit", source="test"),
        ]
        result = scan_keywords(headlines)
        assert result.net_sentiment < 0

    def test_dedup_same_keyword_same_headline(self) -> None:
        """Same keyword in same headline should not double-count."""
        headlines = [
            Headline(title="ETF approved by SEC, ETF launches today", source="test"),
        ]
        result = scan_keywords(headlines)
        # "etf approved" and "etf" may both match, but each only once per headline
        kw_counts = {}
        for h in result.hits:
            kw_counts[h.keyword] = kw_counts.get(h.keyword, 0) + 1
        for kw, count in kw_counts.items():
            assert count == 1, f"Keyword '{kw}' counted {count} times"

    def test_max_hits_limit(self) -> None:
        """Should respect max_hits."""
        headlines = [
            Headline(title=f"Bitcoin ETF hack exploit recession {i}", source="test")
            for i in range(50)
        ]
        result = scan_keywords(headlines, max_hits=5)
        assert len(result.hits) <= 5
