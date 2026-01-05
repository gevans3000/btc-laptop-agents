#!/usr/bin/env python3
"""Collect BTCUSDT 5m candles into a local CSV with Bitunix-first + fallback.

This is intentionally simple:
- Each poll fetches recent candles (default 200).
- Deduplicates by candle timestamp.
- Over time, you build a dataset for backtesting without needing deep pagination.

Usage:
  python scripts/collect_candles.py --out data/btcusdt_5m.csv --minutes 60
  python scripts/collect_candles.py --out data/btcusdt_5m.csv --forever

Notes:
- If Bitunix is blocked, it automatically falls back to Binance Futures public candles.
- You can swap/extend fallback later.
"""

import argparse
import csv
import json
import os
import time
import urllib.request
import urllib.error
from typing import List, Dict, Any, Optional, Tuple

BITUNIX_BASE = "https://fapi.bitunix.com"
BINANCE_BASE = "https://fapi.binance.com"

def http_get_json(url: str, timeout: float = 10.0) -> Tuple[int, Any, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "btc-laptop-agents/candle-collector"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return status, json.loads(raw), raw[:200]
            except Exception:
                return status, None, raw[:200]
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
        try:
            return int(e.code), json.loads(raw) if raw else None, raw[:200]
        except Exception:
            return int(e.code), None, raw[:200]
    except Exception as e:
        return 0, None, str(e)[:200]

def fetch_bitunix_klines(symbol: str, interval: str = "5m", limit: int = 200) -> Optional[List[Dict[str, Any]]]:
    # Bitunix OpenAPI style: {"code":0,"msg":"Success","data":[...]}
    url = f"{BITUNIX_BASE}/api/v1/futures/market/kline?symbol={symbol}&interval={interval}&limit={limit}&type=LAST_PRICE"
    status, data, head = http_get_json(url)
    if status != 200 or not isinstance(data, dict) or data.get("code") != 0:
        return None
    rows = data.get("data")
    if not isinstance(rows, list):
        return None
    out = []
    for r in rows:
        # We accept multiple possible shapes defensively.
        # Common patterns: [ts, open, high, low, close, volume] or dict keys.
        if isinstance(r, list) and len(r) >= 6:
            ts = int(float(r[0]))
            o, h, l, c, v = map(float, r[1:6])
        elif isinstance(r, dict):
            # Try common key variants
            ts = int(float(r.get("ts") or r.get("time") or r.get("timestamp") or 0))
            o = float(r.get("open", 0))
            h = float(r.get("high", 0))
            l = float(r.get("low", 0))
            c = float(r.get("close", 0))
            v = float(r.get("volume", 0) or r.get("vol", 0))
        else:
            continue
        if ts <= 0:
            continue
        out.append({"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": v, "source": "bitunix"})
    return out if out else None

def fetch_binance_klines(symbol: str, interval: str = "5m", limit: int = 1000) -> Optional[List[Dict[str, Any]]]:
    # Binance futures: [[openTime, open, high, low, close, volume, closeTime, ...], ...]
    url = f"{BINANCE_BASE}/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={min(limit,1500)}"
    status, data, head = http_get_json(url)
    if status != 200 or not isinstance(data, list):
        return None
    out = []
    for r in data:
        if not (isinstance(r, list) and len(r) >= 6):
            continue
        ts = int(r[0])
        o = float(r[1]); h=float(r[2]); l=float(r[3]); c=float(r[4]); v=float(r[5])
        out.append({"ts": ts, "open": o, "high": h, "low": l, "close": c, "volume": v, "source": "binance"})
    return out if out else None

def load_existing(path: str) -> Dict[int, Dict[str, Any]]:
    if not os.path.exists(path):
        return {}
    out: Dict[int, Dict[str, Any]] = {}
    with open(path, "r", newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            try:
                ts = int(row["ts"])
            except Exception:
                continue
            out[ts] = row
    return out

def save_csv(path: str, rows: Dict[int, Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fieldnames = ["ts","open","high","low","close","volume","source"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for ts in sorted(rows.keys()):
            r = rows[ts]
            w.writerow({
                "ts": ts,
                "open": r["open"],
                "high": r["high"],
                "low": r["low"],
                "close": r["close"],
                "volume": r["volume"],
                "source": r.get("source",""),
            })

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--interval", default="5m")
    ap.add_argument("--out", default="data/btcusdt_5m.csv")
    ap.add_argument("--poll-seconds", type=int, default=30)
    ap.add_argument("--minutes", type=int, default=0, help="Run for N minutes then exit (0 means use --forever)")
    ap.add_argument("--forever", action="store_true", help="Run forever")
    ap.add_argument("--bitunix-limit", type=int, default=200)
    ap.add_argument("--binance-limit", type=int, default=1000)
    args = ap.parse_args()

    deadline = time.time() + (args.minutes * 60) if args.minutes > 0 else None
    existing = load_existing(args.out)
    print(f"Loaded existing candles: {len(existing)} -> {args.out}")

    while True:
        bit = fetch_bitunix_klines(args.symbol, args.interval, args.bitunix_limit)
        if bit:
            new_rows = bit
            src = "bitunix"
        else:
            bn = fetch_binance_klines(args.symbol, args.interval, args.binance_limit)
            new_rows = bn or []
            src = "binance"
        added = 0
        for r in new_rows:
            ts = int(r["ts"])
            if ts not in existing:
                existing[ts] = r
                added += 1
            else:
                # keep newest values if changed
                existing[ts] = r
        save_csv(args.out, existing)
        print(f"Fetched {len(new_rows):4d} candles from {src:7} | added={added:3d} | total={len(existing)}")
        if deadline and time.time() >= deadline and not args.forever:
            break
        time.sleep(args.poll_seconds)

if __name__ == "__main__":
    main()
