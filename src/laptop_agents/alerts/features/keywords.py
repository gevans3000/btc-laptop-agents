"""Keyword scanner for Trump/policy/macro impact detection in headlines."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List

from laptop_agents.alerts.collectors.news import Headline

logger = logging.getLogger("btc_alerts.features.keywords")

# Keyword groups with impact weight (-1.0 = very bearish, +1.0 = very bullish)
DEFAULT_KEYWORD_GROUPS: Dict[str, Dict[str, float]] = {
    "trump_policy": {
        "trump": 0.0,            # neutral mention, context matters
        "executive order": -0.2,
        "tariff": -0.4,
        "sanction": -0.3,
        "strategic reserve": 0.6,
        "bitcoin reserve": 0.7,
        "crypto ban": -0.8,
        "crypto regulation": -0.3,
        "deregulation": 0.4,
        "pro-crypto": 0.5,
        "anti-crypto": -0.5,
    },
    "macro": {
        "interest rate": -0.2,
        "rate hike": -0.4,
        "rate cut": 0.4,
        "inflation": -0.2,
        "cpi": -0.1,
        "fed": -0.1,
        "recession": -0.5,
        "quantitative easing": 0.4,
        "money printing": 0.3,
        "stimulus": 0.3,
        "debt ceiling": -0.3,
        "default": -0.6,
    },
    "market_events": {
        "etf approved": 0.6,
        "etf rejected": -0.5,
        "etf": 0.1,
        "hack": -0.5,
        "exploit": -0.4,
        "bankruptcy": -0.6,
        "adoption": 0.4,
        "institutional": 0.3,
        "whale": 0.1,
        "halving": 0.3,
        "sec": -0.2,
        "lawsuit": -0.3,
    },
}


@dataclass
class KeywordHit:
    """A single keyword match in a headline."""

    keyword: str
    group: str
    weight: float
    headline: str
    source: str


@dataclass
class KeywordScanResult:
    """Aggregated keyword scan output."""

    hits: List[KeywordHit] = field(default_factory=list)
    net_sentiment: float = 0.0       # sum of weights
    top_keywords: List[str] = field(default_factory=list)
    trump_policy_hit: bool = False


def scan_keywords(
    headlines: List[Headline],
    keyword_groups: Dict[str, Dict[str, float]] | None = None,
    max_hits: int = 20,
) -> KeywordScanResult:
    """Scan headlines for configured keywords and compute net sentiment.

    Returns aggregated result with individual hits, net score, and flags.
    """
    groups = keyword_groups or DEFAULT_KEYWORD_GROUPS
    hits: List[KeywordHit] = []

    for hl in headlines:
        title_lower = hl.title.lower()
        for group_name, kw_map in groups.items():
            for kw, weight in kw_map.items():
                if re.search(r"\b" + re.escape(kw) + r"\b", title_lower):
                    hits.append(
                        KeywordHit(
                            keyword=kw,
                            group=group_name,
                            weight=weight,
                            headline=hl.title,
                            source=hl.source,
                        )
                    )

    # Deduplicate: same keyword + same headline
    seen = set()
    unique_hits: List[KeywordHit] = []
    for h in hits:
        key = (h.keyword, h.headline)
        if key not in seen:
            seen.add(key)
            unique_hits.append(h)

    unique_hits = unique_hits[:max_hits]
    net = sum(h.weight for h in unique_hits)
    trump_hit = any(h.group == "trump_policy" for h in unique_hits)

    # Top keywords by absolute weight
    kw_weights: Dict[str, float] = {}
    for h in unique_hits:
        kw_weights[h.keyword] = kw_weights.get(h.keyword, 0.0) + h.weight
    sorted_kws = sorted(kw_weights.items(), key=lambda x: abs(x[1]), reverse=True)
    top_kws = [k for k, _ in sorted_kws[:5]]

    return KeywordScanResult(
        hits=unique_hits,
        net_sentiment=round(net, 3),
        top_keywords=top_kws,
        trump_policy_hit=trump_hit,
    )
