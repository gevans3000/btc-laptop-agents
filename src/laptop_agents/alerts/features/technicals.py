"""Technical feature extraction for alert scoring.

Reuses the existing ``laptop_agents.indicators.ema`` where possible and adds
lightweight momentum / volatility features on ``SimpleCandle`` lists.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from laptop_agents.indicators import ema as _ema_calc
from laptop_agents.alerts.collectors.price import SimpleCandle

logger = logging.getLogger("btc_alerts.features.technicals")


@dataclass
class TechnicalFeatures:
    """Computed technical features for the scoring engine."""

    price: float = 0.0
    ema_short: Optional[float] = None   # e.g. EMA-12
    ema_long: Optional[float] = None    # e.g. EMA-26
    ema_trend: str = "neutral"          # "bullish" | "bearish" | "neutral"
    volatility_pct: float = 0.0         # recent range as % of price
    momentum_pct: float = 0.0           # % change over lookback
    price_vs_ema_short_pct: float = 0.0  # price distance from short EMA
    healthy: bool = True


def compute_technical_features(
    candles: List[SimpleCandle],
    ema_short_period: int = 12,
    ema_long_period: int = 26,
    vol_lookback: int = 14,
    momentum_lookback: int = 6,
) -> TechnicalFeatures:
    """Compute EMA cross, volatility, momentum from candle list.

    Designed to degrade gracefully if there are insufficient candles.
    """
    if not candles:
        return TechnicalFeatures(healthy=False)

    closes = [c.close for c in candles]
    current_price = closes[-1]

    # EMA calculation reusing repo indicator
    ema_s = _ema_calc(closes, ema_short_period)
    ema_l = _ema_calc(closes, ema_long_period)

    # Trend
    if ema_s is not None and ema_l is not None:
        if ema_s > ema_l * 1.001:
            trend = "bullish"
        elif ema_s < ema_l * 0.999:
            trend = "bearish"
        else:
            trend = "neutral"
    else:
        trend = "neutral"

    # Volatility: (max - min) / price over lookback window
    vol_window = closes[-vol_lookback:] if len(closes) >= vol_lookback else closes
    price_range = max(vol_window) - min(vol_window) if vol_window else 0.0
    volatility_pct = (price_range / current_price * 100) if current_price > 0 else 0.0

    # Momentum: % change from lookback bars ago to now
    if len(closes) > momentum_lookback:
        old_price = closes[-momentum_lookback - 1]
        momentum_pct = ((current_price - old_price) / old_price * 100) if old_price > 0 else 0.0
    else:
        momentum_pct = 0.0

    # Price distance from short EMA
    if ema_s is not None and ema_s > 0:
        price_vs_ema = (current_price - ema_s) / ema_s * 100
    else:
        price_vs_ema = 0.0

    return TechnicalFeatures(
        price=current_price,
        ema_short=ema_s,
        ema_long=ema_l,
        ema_trend=trend,
        volatility_pct=round(volatility_pct, 4),
        momentum_pct=round(momentum_pct, 4),
        price_vs_ema_short_pct=round(price_vs_ema, 4),
        healthy=True,
    )
