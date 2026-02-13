"""Fetch Bitcoin-related headlines from public RSS feeds (no key required)."""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional

import httpx

from laptop_agents.alerts.budget import BudgetManager

logger = logging.getLogger("btc_alerts.collectors.news")

# Free RSS feeds for crypto news
DEFAULT_FEEDS: List[str] = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
]

_DEFAULT_TIMEOUT = 12.0
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class Headline:
    """A single news headline."""

    title: str
    source: str
    published: str = ""
    link: str = ""


@dataclass
class NewsSnapshot:
    """Collection of recent headlines."""

    headlines: List[Headline] = field(default_factory=list)
    timestamp: float = 0.0
    healthy: bool = True
    sources_ok: int = 0
    sources_total: int = 0


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


def _parse_rss(xml_text: str, source: str, max_items: int = 10) -> List[Headline]:
    """Parse RSS XML and return headlines."""
    items: List[Headline] = []
    try:
        root = ET.fromstring(xml_text)
        # Standard RSS 2.0 path
        for item in root.iter("item"):
            title_el = item.find("title")
            link_el = item.find("link")
            pub_el = item.find("pubDate")
            if title_el is not None and title_el.text:
                items.append(
                    Headline(
                        title=_strip_html(title_el.text),
                        source=source,
                        published=pub_el.text if pub_el is not None and pub_el.text else "",
                        link=link_el.text if link_el is not None and link_el.text else "",
                    )
                )
            if len(items) >= max_items:
                break
    except ET.ParseError as exc:
        logger.warning("RSS parse error from %s: %s", source, exc)
    return items


def fetch_news_headlines(
    feeds: Optional[List[str]] = None,
    budget: Optional[BudgetManager] = None,
    timeout: float = _DEFAULT_TIMEOUT,
    max_per_feed: int = 10,
) -> NewsSnapshot:
    """Fetch headlines from configured RSS feeds.

    Degrades gracefully per-feed; returns whatever succeeds.
    """
    feed_urls = feeds or DEFAULT_FEEDS
    all_headlines: List[Headline] = []
    ok_count = 0

    for url in feed_urls:
        source_name = url.split("/")[2] if len(url.split("/")) > 2 else url
        if budget and not budget.can_call("rss"):
            logger.warning("Budget exhausted for RSS; skipping %s", source_name)
            continue
        try:
            if budget:
                budget.record_call("rss")
            resp = httpx.get(url, timeout=timeout, follow_redirects=True)
            resp.raise_for_status()
            items = _parse_rss(resp.text, source_name, max_per_feed)
            all_headlines.extend(items)
            ok_count += 1
        except Exception as exc:
            logger.warning("RSS feed %s failed: %s", source_name, exc)

    return NewsSnapshot(
        headlines=all_headlines,
        timestamp=time.time(),
        healthy=ok_count > 0,
        sources_ok=ok_count,
        sources_total=len(feed_urls),
    )
