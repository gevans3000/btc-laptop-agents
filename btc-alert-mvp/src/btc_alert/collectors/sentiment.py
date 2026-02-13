from datetime import datetime, timezone


def collect_sentiment_snapshot(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "sentiment_score": 0.0,
        "label": "neutral",
        "source": "mvp-placeholder",
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
