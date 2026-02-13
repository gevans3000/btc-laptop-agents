from __future__ import annotations

from pathlib import Path

from laptop_agents.data.free_collectors import FreeDataCollectors


class _Resp:
    def __init__(self, body: str):
        self._b = body.encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


def test_collectors_offline_safe_partial(monkeypatch):
    def fake_urlopen(url, timeout=0):
        u = str(url)
        if "binance" in u:
            return _Resp("[[1,\"100\",\"101\",\"99\",\"100.5\",\"123\"]]")
        if "alternative.me" in u:
            return _Resp('{"data":[{"value":"55","value_classification":"Greed","timestamp":"1"}]}')
        raise OSError("feed down")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    c = FreeDataCollectors(offline_safe=True)
    out = c.collect_all("BTC")

    assert out["price_ohlc"]
    assert out["fear_greed"]["value"] == 55
    assert out["news"] is None
    assert out["social_sentiment"] is None
    assert out["degraded_mode"] is True
    assert out["source_health"]["news"]["ok"] is False


def test_collectors_hourly_quota_respected(monkeypatch, tmp_path: Path):
    cfg = tmp_path / "limits.yaml"
    cfg.write_text(
        """
sources:
  price_ohlc:
    budget_per_hour: 1
    timeout_seconds: 2
    fallback_order: [binance_klines_public]
  fear_greed:
    budget_per_hour: 1
    timeout_seconds: 2
    fallback_order: [alternative_me]
  news:
    budget_per_hour: 1
    timeout_seconds: 2
    fallback_order: [coindesk_rss]
    feeds: [https://www.coindesk.com/arc/outboundfeeds/rss/]
  social_sentiment:
    budget_per_hour: 1
    timeout_seconds: 2
    fallback_order: [reddit_search_rss]
    feeds: ["https://www.reddit.com/search.rss?q={keyword}&sort=new"]
""".strip(),
        encoding="utf-8",
    )

    def fake_urlopen(url, timeout=0):
        u = str(url)
        if "binance" in u:
            return _Resp("[[1,\"100\",\"101\",\"99\",\"100.5\",\"123\"]]")
        if "alternative.me" in u:
            return _Resp('{"data":[{"value":"40","value_classification":"Fear","timestamp":"1"}]}')
        return _Resp("<rss><channel><item><title>bitcoin rally</title><link>x</link></item></channel></rss>")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    c = FreeDataCollectors(limits_path=cfg, offline_safe=True)
    first = c.collect_all("BTC")
    second = c.collect_all("BTC")

    assert first["source_health"]["price_ohlc"]["ok"] is True
    assert second["source_health"]["price_ohlc"]["quota_exhausted"] is True
