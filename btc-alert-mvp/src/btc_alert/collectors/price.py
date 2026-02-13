import httpx

from btc_alert.core.rate_limiter import RateLimiter
from btc_alert.resilience import RetryPolicy, with_retry

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
_limiter = RateLimiter(name="binance")


@with_retry(RetryPolicy(max_attempts=3, base_delay=0.5), "fetch_klines")
def fetch_klines(symbol: str, interval: str = "5m", limit: int = 100) -> list[float]:
    _limiter.wait_sync()
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    with httpx.Client(timeout=10) as client:
        resp = client.get(BINANCE_KLINES, params=params)
        resp.raise_for_status()
        rows = resp.json()
    return [float(r[4]) for r in rows]
