"""Fetch BTC price and candles from Binance public API (no key required)."""

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


def fetch_btc_price(
    budget: Optional[BudgetManager] = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> PriceSnapshot:
    """Fetch current BTC/USDT price from Binance ticker.

    Returns a PriceSnapshot; on failure returns a degraded snapshot with
    ``healthy=False`` and ``price=0.0``.
    """
    if budget and not budget.can_call("binance"):
        logger.warning("Budget exhausted for binance; returning degraded price")
        return PriceSnapshot(price=0.0, timestamp=time.time(), healthy=False)

    try:
        if budget:
            budget.record_call("binance")
        resp = httpx.get(
            TICKER_URL, params={"symbol": "BTCUSDT"}, timeout=timeout
        )
        resp.raise_for_status()
        data: Dict[str, Any] = resp.json()
        return PriceSnapshot(
            price=float(data["price"]),
            timestamp=time.time(),
        )
    except Exception as exc:
        logger.error("Binance price fetch failed: %s", exc)
        return PriceSnapshot(price=0.0, timestamp=time.time(), healthy=False)


def fetch_btc_candles(
    interval: str = "1h",
    limit: int = 50,
    budget: Optional[BudgetManager] = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> List[SimpleCandle]:
    """Fetch recent BTC/USDT candles from Binance klines endpoint.

    Returns list of ``SimpleCandle`` (oldest-first).  On failure returns [].
    """
    if budget and not budget.can_call("binance"):
        logger.warning("Budget exhausted for binance; returning empty candles")
        return []

    try:
        if budget:
            budget.record_call("binance")
        resp = httpx.get(
            KLINES_URL,
            params={"symbol": "BTCUSDT", "interval": interval, "limit": limit},
            timeout=timeout,
        )
        resp.raise_for_status()
        raw: List[List[Any]] = resp.json()
        candles: List[SimpleCandle] = []
        for k in raw:
            candles.append(
                SimpleCandle(
                    ts=float(k[0]) / 1000.0,
                    open=float(k[1]),
                    high=float(k[2]),
                    low=float(k[3]),
                    close=float(k[4]),
                    volume=float(k[5]),
                )
            )
        return candles
    except Exception as exc:
        logger.error("Binance klines fetch failed: %s", exc)
        return []
