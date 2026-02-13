"""Fetch Bitcoin Fear & Greed Index from Alternative.me (free, no key)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from laptop_agents.alerts.budget import BudgetManager

logger = logging.getLogger("btc_alerts.collectors.fear_greed")

FG_URL = "https://api.alternative.me/fng/?limit=1&format=json"
_DEFAULT_TIMEOUT = 10.0


@dataclass
class FearGreedSnapshot:
    """Fear & Greed index reading."""

    value: int  # 0-100
    label: str  # e.g. "Extreme Fear", "Greed"
    timestamp: float
    healthy: bool = True


def fetch_fear_greed(
    budget: Optional[BudgetManager] = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> FearGreedSnapshot:
    """Return the latest Fear & Greed reading.

    On failure returns a degraded snapshot with ``value=50`` (neutral).
    """
    if budget and not budget.can_call("alternative_me"):
        logger.warning("Budget exhausted for alternative.me; returning neutral FG")
        return FearGreedSnapshot(value=50, label="Neutral (degraded)", timestamp=time.time(), healthy=False)

    try:
        if budget:
            budget.record_call("alternative_me")
        resp = httpx.get(FG_URL, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        entry = data["data"][0]
        return FearGreedSnapshot(
            value=int(entry["value"]),
            label=entry.get("value_classification", "Unknown"),
            timestamp=float(entry.get("timestamp", time.time())),
        )
    except Exception as exc:
        logger.error("Fear & Greed fetch failed: %s", exc)
        return FearGreedSnapshot(value=50, label="Neutral (degraded)", timestamp=time.time(), healthy=False)
