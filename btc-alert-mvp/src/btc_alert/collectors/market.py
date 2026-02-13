import httpx

from btc_alert.core.rate_limiter import RateLimiter
from btc_alert.resilience import RetryPolicy, with_retry

TICKER_24H = "https://api.binance.com/api/v3/ticker/24hr"
_limiter = RateLimiter(name="market")


@with_retry(RetryPolicy(max_attempts=3, base_delay=0.5), "fetch_market_snapshot")
def fetch_market_snapshot(symbol: str) -> dict:
    _limiter.wait_sync()
    with httpx.Client(timeout=10) as client:
        resp = client.get(TICKER_24H, params={"symbol": symbol})
        resp.raise_for_status()
        data = resp.json()
    return {
        "symbol": symbol,
        "last_price": float(data["lastPrice"]),
        "price_change_percent": float(data["priceChangePercent"]),
        "quote_volume": float(data["quoteVolume"]),
    }
