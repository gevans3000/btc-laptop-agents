from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import parse, request
from xml.etree import ElementTree

import yaml

from laptop_agents.core.rate_limiter import RateLimiter
from laptop_agents.resilience.retry import RetryPolicy, with_retry

DEFAULT_LIMITS_PATH = Path(__file__).resolve().parents[3] / "config" / "free_limits.yaml"


@dataclass
class SourceResult:
    name: str
    ok: bool
    degraded: bool
    latency_ms: int
    quota_exhausted: bool
    reason: str = ""


class HourlyQuota:
    def __init__(self, max_per_hour: int) -> None:
        self.max_per_hour = max_per_hour
        self.window_start = time.time()
        self.used = 0

    def allow(self) -> bool:
        now = time.time()
        if now - self.window_start >= 3600:
            self.window_start = now
            self.used = 0
        if self.used >= self.max_per_hour:
            return False
        self.used += 1
        return True


class FreeDataCollectors:
    def __init__(self, limits_path: Path | None = None, offline_safe: bool = False) -> None:
        self.offline_safe = offline_safe
        self.config = self._load_limits(limits_path or DEFAULT_LIMITS_PATH)
        self.retry_policy = RetryPolicy(max_attempts=3, base_delay=0.2)

        self.limiters = {
            src: RateLimiter(
                sustained_rps=max(0.1, float(cfg["budget_per_hour"]) / 3600.0),
                burst=max(1.0, min(5.0, float(cfg["budget_per_hour"]) / 10.0)),
                name=f"free-{src}",
            )
            for src, cfg in self.config["sources"].items()
        }
        self.quotas = {
            src: HourlyQuota(int(cfg["budget_per_hour"]))
            for src, cfg in self.config["sources"].items()
        }

    def collect_all(self, symbol: str = "BTC") -> Dict[str, Any]:
        source_health: Dict[str, Dict[str, Any]] = {}
        payload: Dict[str, Any] = {"source_health": source_health, "symbol": symbol}

        payload["price_ohlc"] = self._guarded_collect("price_ohlc", source_health, self._collect_binance_ohlc(symbol))
        payload["fear_greed"] = self._guarded_collect("fear_greed", source_health, self._collect_fear_greed)
        payload["news"] = self._guarded_collect("news", source_health, self._collect_news(symbol))
        payload["social_sentiment"] = self._guarded_collect(
            "social_sentiment", source_health, self._collect_social_sentiment(symbol)
        )

        payload["degraded_mode"] = any(not item["ok"] for item in source_health.values())
        return payload

    def _guarded_collect(self, source: str, health: Dict[str, Dict[str, Any]], fn: Any) -> Any:
        cfg = self.config["sources"][source]
        started = time.time()

        if not self.quotas[source].allow():
            health[source] = SourceResult(
                name=source,
                ok=False,
                degraded=True,
                latency_ms=0,
                quota_exhausted=True,
                reason="hourly_quota_exhausted",
            ).__dict__
            return None

        self.limiters[source].wait_sync()

        try:
            result = self._with_timeout(fn, timeout_s=float(cfg["timeout_seconds"]))
            health[source] = SourceResult(
                name=source,
                ok=True,
                degraded=False,
                latency_ms=int((time.time() - started) * 1000),
                quota_exhausted=False,
            ).__dict__
            return result
        except Exception as exc:
            health[source] = SourceResult(
                name=source,
                ok=False,
                degraded=True,
                latency_ms=int((time.time() - started) * 1000),
                quota_exhausted=False,
                reason=str(exc),
            ).__dict__
            if self.offline_safe:
                return None
            raise RuntimeError(f"source '{source}' unavailable: {exc}") from exc

    def _with_timeout(self, fn: Any, timeout_s: float) -> Any:
        start = time.time()
        result = fn(timeout_s)
        if time.time() - start > timeout_s:
            raise TimeoutError(f"timeout>{timeout_s}s")
        return result

    def _read_json(self, url: str, timeout_s: float) -> Dict[str, Any]:
        @with_retry(self.retry_policy, "read_json")
        def _inner() -> Dict[str, Any]:
            with request.urlopen(url, timeout=timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))

        return _inner()

    def _read_xml(self, url: str, timeout_s: float) -> ElementTree.Element:
        @with_retry(self.retry_policy, "read_xml")
        def _inner() -> ElementTree.Element:
            with request.urlopen(url, timeout=timeout_s) as resp:
                return ElementTree.fromstring(resp.read())

        return _inner()

    def _collect_binance_ohlc(self, symbol: str) -> Any:
        def _inner(timeout_s: float) -> Any:
            endpoint = (
                "https://api.binance.com/api/v3/klines?symbol="
                f"{symbol.upper()}USDT&interval=1h&limit=24"
            )
            data = self._read_json(endpoint, timeout_s)
            if not data:
                return []
            return [
                {
                    "open_time": row[0],
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
                for row in data
            ]

        return _inner

    def _collect_fear_greed(self, timeout_s: float) -> Any:
        data = self._read_json("https://api.alternative.me/fng/?limit=1", timeout_s)
        item = (data.get("data") or [{}])[0]
        return {
            "value": int(item.get("value", 0)),
            "classification": item.get("value_classification", "unknown"),
            "timestamp": item.get("timestamp"),
        }

    def _keyword_score(self, text: str, positive: List[str], negative: List[str]) -> int:
        lowered = text.lower()
        return sum(1 for w in positive if w in lowered) - sum(1 for w in negative if w in lowered)

    def _collect_news(self, symbol: str):
        def _inner(timeout_s: float) -> Any:
            feeds = self.config["sources"]["news"]["feeds"]
            positive = ["surge", "rally", "approval", "gain", "bull"]
            negative = ["hack", "ban", "drop", "loss", "bear"]
            out: List[Dict[str, Any]] = []
            for url in feeds:
                root = self._read_xml(url, timeout_s)
                for item in root.findall(".//item")[:8]:
                    title = item.findtext("title") or ""
                    link = item.findtext("link") or ""
                    if symbol.lower() not in title.lower() and "bitcoin" not in title.lower():
                        continue
                    out.append({"title": title, "link": link, "score": self._keyword_score(title, positive, negative)})
            out.sort(key=lambda x: x["score"], reverse=True)
            return out[:15]

        return _inner

    def _collect_social_sentiment(self, symbol: str):
        def _inner(timeout_s: float) -> Any:
            endpoints = self.config["sources"]["social_sentiment"]["feeds"]
            keyword = parse.quote(symbol.lower())
            mentions = 0
            samples: List[str] = []
            for url in endpoints:
                final_url = url.replace("{keyword}", keyword)
                root = self._read_xml(final_url, timeout_s)
                titles = [item.findtext("title") or "" for item in root.findall(".//item")[:20]]
                if titles:
                    mentions += len(titles)
                    samples.extend(titles[:3])
            return {"mentions": mentions, "sample_titles": samples[:6]}

        return _inner

    @staticmethod
    def _load_limits(path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        if "sources" not in cfg:
            raise ValueError("free_limits.yaml missing sources")
        return cfg
