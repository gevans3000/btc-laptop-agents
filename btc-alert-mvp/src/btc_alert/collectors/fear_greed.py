import httpx

from btc_alert.core.rate_limiter import RateLimiter
from btc_alert.resilience import RetryPolicy, with_retry

FGI_URL = "https://api.alternative.me/fng/"
_limiter = RateLimiter(name="fear-greed")


@with_retry(RetryPolicy(max_attempts=3, base_delay=0.5), "fetch_fear_greed")
def fetch_fear_greed() -> dict:
    _limiter.wait_sync()
    with httpx.Client(timeout=10) as client:
        resp = client.get(FGI_URL, params={"limit": 1})
        resp.raise_for_status()
        data = resp.json()["data"][0]
    return {"value": int(data["value"]), "classification": data["value_classification"]}
