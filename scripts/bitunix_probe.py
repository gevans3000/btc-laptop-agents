#!/usr/bin/env python3
"""Bitunix Phase-0 probe (no deps).

Confirms your machine/network can reach Bitunix futures market data endpoints needed for
5m candles, tickers, and funding.

Usage:
  python scripts/bitunix_probe.py --symbol BTCUSDT --interval 5m --limit 5 --repeats 3
  python scripts/bitunix_probe.py --json-out probe_results.json
"""

import argparse
import json
import time
import urllib.request
import urllib.error
from typing import Any, Dict, Tuple

BASE = "https://fapi.bitunix.com"

def fetch(url: str, timeout: float = 10.0) -> Tuple[int, Dict[str, Any], str, float]:
    t0 = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "btc-laptop-agents/phase0-probe"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            body = resp.read()
            elapsed = time.time() - t0
            text = body.decode("utf-8", errors="replace")
            head = text[:200]
            try:
                data = json.loads(text)
            except Exception:
                data = {}
            return status, data, head, elapsed
    except urllib.error.HTTPError as e:
        elapsed = time.time() - t0
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        head = body[:200]
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}
        return int(e.code), data, head, elapsed
    except Exception as e:
        elapsed = time.time() - t0
        return 0, {"error": str(e)}, str(e)[:200], elapsed

def classify(status: int, data: Dict[str, Any], head: str) -> str:
    if status == 200 and isinstance(data, dict) and ("code" in data or "data" in data):
        if data.get("code", 0) == 0:
            return "OK"
        return "JSON_NONZERO_CODE"
    if status in (401, 403):
        return "BLOCKED_OR_AUTH"
    if status == 429:
        return "RATE_LIMIT"
    if status == 0:
        return "NETWORK_ERROR"
    if head and "<html" in head.lower():
        return "HTML_BLOCKED_OR_WAF"
    return f"HTTP_{status or 'ERR'}"

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--interval", default="5m")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    endpoints = [
        ("tickers", f"{BASE}/api/v1/futures/market/tickers?symbols={args.symbol}"),
        ("kline", f"{BASE}/api/v1/futures/market/kline?symbol={args.symbol}&interval={args.interval}&limit={args.limit}&type=LAST_PRICE"),
        ("funding_rate", f"{BASE}/api/v1/futures/market/funding_rate?symbol={args.symbol}"),
    ]

    results = {"base": BASE, "symbol": args.symbol, "runs": []}

    print(f"Bitunix Phase-0 Probe | base={BASE} symbol={args.symbol} repeats={args.repeats}")
    for i in range(args.repeats):
        run = {"i": i + 1, "checks": []}
        print(f"\n--- Run {i+1}/{args.repeats} ---")
        for name, url in endpoints:
            status, data, head, elapsed = fetch(url, timeout=args.timeout)
            cls = classify(status, data, head)
            msg = ""
            if isinstance(data, dict):
                msg = str(data.get("msg", ""))[:60]
            print(f"{name:12} status={status:>3}  {cls:18}  {elapsed:5.2f}s  msg={msg}")
            run["checks"].append({
                "name": name,
                "url": url,
                "status": status,
                "class": cls,
                "elapsed_s": round(elapsed, 4),
                "msg": msg,
                "json_keys": sorted(list(data.keys())) if isinstance(data, dict) else [],
                "head": head,
            })
        results["runs"].append(run)
        time.sleep(0.4)

    classes = [c["class"] for r in results["runs"] for c in r["checks"]]
    ok = classes.count("OK")
    total = len(classes)
    print(f"\nSummary: OK={ok}/{total}")
    if ok == total:
        print("Overall: GREEN (Bitunix usable)")
    elif ok > 0:
        print("Overall: YELLOW (intermittent; build Router + cooldown + fallback)")
    else:
        print("Overall: RED (blocked/unreachable; must use fallback provider, Bitunix optional)")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"Wrote: {args.json_out}")

if __name__ == "__main__":
    main()
