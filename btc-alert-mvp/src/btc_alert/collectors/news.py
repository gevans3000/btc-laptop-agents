from datetime import datetime, timezone


def collect_news_snapshot(symbol: str) -> dict:
    # MVP placeholder hook for real RSS/news API integration.
    return {
        "symbol": symbol,
        "headline_count_1h": 0,
        "latest_headline": "No integrated news feed in MVP",
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
