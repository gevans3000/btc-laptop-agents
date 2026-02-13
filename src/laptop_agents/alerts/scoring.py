"""Deterministic scoring engine for BTC alerts.

Combines technical, sentiment, keyword, and fear/greed signals into a
single confidence score (0–100) with ranked human-readable reasons.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from laptop_agents.alerts.features.technicals import TechnicalFeatures
from laptop_agents.alerts.features.keywords import KeywordScanResult
from laptop_agents.alerts.collectors.fear_greed import FearGreedSnapshot

logger = logging.getLogger("btc_alerts.scoring")


@dataclass
class Reason:
    """A single scored reason for the alert."""

    text: str
    weight: float  # contribution to confidence
    category: str  # "technical", "sentiment", "keyword", "fear_greed"


@dataclass
class AlertScore:
    """Final scored alert output."""

    regime: str = "neutral"            # "bullish" | "bearish" | "neutral"
    confidence: int = 50               # 0-100
    reasons: List[Reason] = field(default_factory=list)
    top_reasons: List[str] = field(default_factory=list)  # human-readable, ranked
    trump_summary: str = ""
    data_quality: str = "ok"           # "ok" | "degraded" | "minimal"
    degraded_sources: List[str] = field(default_factory=list)


def compute_score(
    technicals: TechnicalFeatures,
    keywords: KeywordScanResult,
    fear_greed: Optional[FearGreedSnapshot] = None,
) -> AlertScore:
    """Compute a deterministic alert score from collected features.

    Scoring logic:
    - Technical trend contributes ±15 confidence
    - Momentum magnitude contributes ±15
    - Volatility contributes ±10
    - Fear & Greed contributes ±15
    - Keyword net sentiment contributes ±15
    - Baseline is 50 (neutral)
    """
    reasons: List[Reason] = []
    bias = 0.0  # positive = bullish, negative = bearish
    degraded: List[str] = []

    # --- Technical signals ---
    if not technicals.healthy:
        degraded.append("price/candles")
    else:
        # EMA trend
        if technicals.ema_trend == "bullish":
            w = 15.0
            reasons.append(Reason(
                text=f"EMA cross bullish (short {technicals.ema_short:.0f} > long {technicals.ema_long:.0f})",
                weight=w, category="technical",
            ))
            bias += w
        elif technicals.ema_trend == "bearish":
            w = -15.0
            reasons.append(Reason(
                text=f"EMA cross bearish (short {technicals.ema_short:.0f} < long {technicals.ema_long:.0f})",
                weight=w, category="technical",
            ))
            bias += w

        # Momentum
        mom = technicals.momentum_pct
        if abs(mom) > 0.5:
            w = min(max(mom * 3, -15), 15)
            direction = "up" if mom > 0 else "down"
            reasons.append(Reason(
                text=f"Momentum {direction} {abs(mom):.2f}% over recent bars",
                weight=w, category="technical",
            ))
            bias += w

        # Volatility
        vol = technicals.volatility_pct
        if vol > 3.0:
            w = -10.0  # high vol = uncertainty
            reasons.append(Reason(
                text=f"High volatility ({vol:.2f}%) – uncertainty elevated",
                weight=w, category="technical",
            ))
            bias += w
        elif vol > 1.5:
            w = -5.0
            reasons.append(Reason(
                text=f"Moderate volatility ({vol:.2f}%)",
                weight=w, category="technical",
            ))
            bias += w

    # --- Fear & Greed ---
    if fear_greed is not None:
        if not fear_greed.healthy:
            degraded.append("fear_greed")
        else:
            fg = fear_greed.value
            if fg <= 25:
                w = 10.0  # extreme fear is contrarian bullish
                reasons.append(Reason(
                    text=f"Extreme Fear ({fg}) – contrarian bullish signal",
                    weight=w, category="fear_greed",
                ))
                bias += w
            elif fg <= 40:
                w = 5.0
                reasons.append(Reason(
                    text=f"Fear ({fg}) – mild contrarian bullish",
                    weight=w, category="fear_greed",
                ))
                bias += w
            elif fg >= 80:
                w = -10.0  # extreme greed is contrarian bearish
                reasons.append(Reason(
                    text=f"Extreme Greed ({fg}) – contrarian bearish signal",
                    weight=w, category="fear_greed",
                ))
                bias += w
            elif fg >= 60:
                w = -5.0
                reasons.append(Reason(
                    text=f"Greed ({fg}) – mild contrarian bearish",
                    weight=w, category="fear_greed",
                ))
                bias += w

    # --- Keywords ---
    kw_net = keywords.net_sentiment
    if abs(kw_net) > 0.1:
        w = min(max(kw_net * 15, -15), 15)
        direction = "positive" if kw_net > 0 else "negative"
        reasons.append(Reason(
            text=f"News keyword sentiment {direction} ({kw_net:+.2f})",
            weight=w, category="keyword",
        ))
        bias += w

    if keywords.trump_policy_hit:
        trump_kws = [h.keyword for h in keywords.hits if h.group == "trump_policy"]
        trump_str = ", ".join(sorted(set(trump_kws)))
    else:
        trump_str = ""

    # --- Regime & confidence ---
    if bias > 5:
        regime = "bullish"
    elif bias < -5:
        regime = "bearish"
    else:
        regime = "neutral"

    # Confidence: 50 + bias, clamped to [0, 100]
    confidence = int(min(100, max(0, 50 + bias)))

    # Data quality
    if len(degraded) >= 2:
        dq = "minimal"
    elif degraded:
        dq = "degraded"
    else:
        dq = "ok"

    # Sort reasons by absolute weight
    reasons.sort(key=lambda r: abs(r.weight), reverse=True)
    top = [r.text for r in reasons[:5]]

    return AlertScore(
        regime=regime,
        confidence=confidence,
        reasons=reasons,
        top_reasons=top,
        trump_summary=trump_str,
        data_quality=dq,
        degraded_sources=degraded,
    )
