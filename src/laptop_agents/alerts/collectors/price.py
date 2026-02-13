"""Fetch BTC price and candles from free public APIs (no key required).

Tries Binance first, falls back to CoinGecko if geo-restricted.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from laptop_agents.alerts.budget import BudgetManager

logger = logging.getLogger("btc_alerts.collectors.price")

BINANCE_BASE = "https://api.binance.com"
TICKER_URL = f"{BINANCE_BASE}/api/v3/ticker/price"
KLINES_URL = f"{BINANCE_BASE}/api/v3/klines"

COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_MARKET_URL = "https://api.coingecko.com/api/v3/coins/bitcoin/ohlc"

_DEFAULT_TIMEOUT = 10.0


@dataclass
class PriceSnapshot:
    """Minimal BTC price snapshot."""

    price: float
    timestamp: float  # unix epoch
    source: str = "binance"
    healthy: bool = True


@dataclass
class SimpleCandle:
    """Lightweight candle for alert features (no trading dependency)."""

    ts: float
    open: float
    high: float
    low: float
    close: float
    volume: float


def _fetch_binance_price(timeout: float) -> Optional[PriceSnapshot]:
    """Try Binance ticker."""
    try:
        resp = httpx.get(
            TICKER_URL, params={"symbol": "BTCUSDT"}, timeout=timeout
        )
        resp.raise_for_status()
        data: Dict[str, Any] = resp.json()
        return PriceSnapshot(
            price=float(data["price"]),
            timestamp=time.time(),
            source="binance",
        )
    except Exception as exc:
        logger.warning("Binance price fetch failed: %s", exc)
        return None


def _fetch_coingecko_price(timeout: float) -> Optional[PriceSnapshot]:
    """Fallback: CoinGecko simple price (free, no key)."""
    try:
        resp = httpx.get(
            COINGECKO_PRICE_URL,
            params={"ids": "bitcoin", "vs_currencies": "usd"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        price = float(data["bitcoin"]["usd"])
        return PriceSnapshot(
            price=price,
            timestamp=time.time(),
            source="coingecko",
        )
    except Exception as exc:
        logger.warning("CoinGecko price fetch failed: %s", exc)
        return None


def fetch_btc_price(
    budget: Optional[BudgetManager] = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> PriceSnapshot:
    """Fetch current BTC/USD price. Tries Binance, then CoinGecko.

    Returns a PriceSnapshot; on total failure returns degraded with price=0.
    """
    if budget and not budget.can_call("binance"):
        logger.warning("Budget exhausted for binance; trying CoinGecko")
    else:
        if budget:
            budget.record_call("binance")
        snap = _fetch_binance_price(timeout)
        if snap:
            return snap

    # Fallback to CoinGecko
    snap = _fetch_coingecko_price(timeout)
    if snap:
        return snap

    return PriceSnapshot(price=0.0, timestamp=time.time(), healthy=False)


def _fetch_binance_candles(
    interval: str, limit: int, timeout: float
) -> Optional[List[SimpleCandle]]:
    """Try Binance klines."""
    try:
        resp = httpx.get(
            KLINES_URL,
            params={"symbol": "BTCUSDT", "interval": interval, "limit": limit},
            timeout=timeout,
        )
        resp.raise_for_status()
        raw: List[List[Any]] = resp.json()
        return [
            SimpleCandle(
                ts=float(k[0]) / 1000.0,
                open=float(k[1]),
                high=float(k[2]),
                low=float(k[3]),
                close=float(k[4]),
                volume=float(k[5]),
            )
            for k in raw
        ]
    except Exception as exc:
        logger.warning("Binance klines fetch failed: %s", exc)
        return None


def _fetch_coingecko_ohlc(
    days: int, timeout: float
) -> Optional[List[SimpleCandle]]:
    """Fallback: CoinGecko OHLC (free, no key). Returns ~hourly candles."""
    try:
        resp = httpx.get(
            COINGECKO_MARKET_URL,
            params={"vs_currency": "usd", "days": days},
            timeout=timeout,
        )
        resp.raise_for_status()
        raw: List[List[float]] = resp.json()
        return [
            SimpleCandle(
                ts=float(k[0]) / 1000.0,
                open=float(k[1]),
                high=float(k[2]),
                low=float(k[3]),
                close=float(k[4]),
                volume=0.0,  # CoinGecko OHLC doesn't include volume
            )
            for k in raw
        ]
    except Exception as exc:
        logger.warning("CoinGecko OHLC fetch failed: %s", exc)
        return None


def fetch_btc_candles(
    interval: str = "1h",
    limit: int = 50,
    budget: Optional[BudgetManager] = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> List[SimpleCandle]:
    """Fetch recent BTC/USDT candles. Tries Binance, then CoinGecko.

    Returns list of ``SimpleCandle`` (oldest-first). On total failure returns [].
    """
    if budget and not budget.can_call("binance"):
        logger.warning("Budget exhausted for binance candles; trying CoinGecko")
    else:
        if budget:
            budget.record_call("binance")
        candles = _fetch_binance_candles(interval, limit, timeout)
        if candles:
            return candles

    # Fallback: CoinGecko OHLC (1 day ≈ 48 half-hour candles)
    candles = _fetch_coingecko_ohlc(days=1, timeout=timeout)
    if candles:
        return candles[-limit:] if len(candles) > limit else candles

    return []
