from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta
from typing import List
import tenacity
from laptop_agents.core.rate_limiter import exchange_rate_limiter

from laptop_agents.trading.helpers import Candle

def load_mock_candles(n: int = 200) -> List[Candle]:
    """Generate fake market data for testing."""
    candles: List[Candle] = []
    price = 100_000.0
    random.seed(42)  # Deterministic mock
    
    for i in range(n):
        # Add a trend + some significant noise to hit limits
        price += 10.0 + (random.random() - 0.5) * 400.0
        
        # Wider wick range (ATR-like)
        range_size = 300.0 + random.random() * 200.0
        o = price - (random.random() - 0.5) * range_size * 0.5
        c = price + (random.random() - 0.5) * range_size * 0.5
        h = max(o, c) + random.random() * range_size * 0.4
        l = min(o, c) - random.random() * range_size * 0.4
        
        # Use real timestamps for Plotly compatibility
        ts_obj = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i)
        candles.append(Candle(ts=ts_obj.isoformat(), open=o, high=h, low=l, close=c, volume=1.0))
    return candles


import os

def _get_bitunix_provider_class():
    """Helper to find the Bitunix provider class in the providers module and its keys."""
    import laptop_agents.data.providers.bitunix_futures as m
    api_key = os.getenv("BITUNIX_API_KEY")
    secret_key = os.getenv("BITUNIX_SECRET") or os.getenv("BITUNIX_SECRET_KEY")
    
    provider_cls = None
    for name in dir(m):
        obj = getattr(m, name)
        if isinstance(obj, type) and hasattr(obj, "klines"):
            provider_cls = obj
            break
            
    if not provider_cls:
        raise RuntimeError("No Bitunix provider class with .klines() found in laptop_agents.data.providers.bitunix_futures")
    
    return provider_cls, api_key, secret_key


@tenacity.retry(
    stop=tenacity.stop_after_attempt(3),
    wait=tenacity.wait_exponential(min=2, max=10),
    retry=tenacity.retry_if_exception_type(Exception)
)
def load_bitunix_candles(symbol: str, interval: str, limit: int) -> List[Candle]:
    """Fetch candles from Bitunix API (supports paged fetching for limits > 200)."""
    # Rate limiting
    exchange_rate_limiter.wait_sync()

    Provider, api_key, secret_key = _get_bitunix_provider_class()
    client = Provider(symbol=symbol, api_key=api_key, secret_key=secret_key)
    # Use paged fetch to support limits > 200
    rows = client.klines_paged(interval=interval, total=int(limit))

    out: List[Candle] = []
    for c in rows:
        ts = getattr(c, "ts", None) or getattr(c, "time", None) or getattr(c, "timestamp", None) or ""
        o = float(getattr(c, "open"))
        h = float(getattr(c, "high"))
        l = float(getattr(c, "low"))
        cl = float(getattr(c, "close"))
        v = float(getattr(c, "volume", 0.0) or 0.0)
        out.append(Candle(ts=str(ts), open=o, high=h, low=l, close=cl, volume=v))
    return out


def get_candles_for_mode(
    source: str,
    symbol: str,
    interval: str,
    mode: str,
    limit: int,
    validate_train: int = 600,
    validate_test: int = 200,
    validate_splits: int = 5
) -> List[Candle]:
    """Orchestrate candle loading based on execution mode."""
    from laptop_agents.trading.helpers import normalize_candle_order
    
    if source == "bitunix":
        if mode == "validate":
            total_needed = validate_splits * (validate_train + validate_test)
            try:
                Provider, api_key, secret_key = _get_bitunix_provider_class()
                client = Provider(symbol=symbol, api_key=api_key, secret_key=secret_key)
                candles = client.klines_paged(interval=interval, total=total_needed)
            except Exception:
                # Fallback to standard paged fetch
                candles = load_bitunix_candles(symbol, interval, limit)
        else:
            candles = load_bitunix_candles(symbol, interval, limit)
    else:
        actual_limit = limit
        if mode == "validate":
            actual_limit = validate_splits * (validate_train + validate_test)
        candles = load_mock_candles(max(int(actual_limit), 50))

    return normalize_candle_order(candles)
