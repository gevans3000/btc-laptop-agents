#!/usr/bin/env python3
"""Backtest: EMA50 trend filter + Donchian20 breakout + ATR stops/targets.

Inputs: CSV from collect_candles.py (ts, open, high, low, close, volume, source)

Outputs:
- prints summary
- writes trades CSV + report JSON

Usage:
  python scripts/backtest_breakout_ema_atr.py --in data/btcusdt_5m.csv --outdir reports
"""

import argparse
import csv
import json
import math
import os
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

@dataclass
class Candle:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float

def read_candles(path: str) -> List[Candle]:
    out: List[Candle] = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for row in rdr:
            try:
                out.append(Candle(
                    ts=int(row["ts"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0),
                ))
            except Exception:
                continue
    out.sort(key=lambda c: c.ts)
    return out

def ema(values: List[float], period: int) -> List[float]:
    k = 2 / (period + 1)
    out: List[float] = []
    e = values[0]
    out.append(e)
    for v in values[1:]:
        e = v * k + e * (1 - k)
        out.append(e)
    return out

def true_range(c: Candle, prev: Candle) -> float:
    return max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close))

def atr(candles: List[Candle], period: int) -> List[float]:
    trs: List[float] = [candles[0].high - candles[0].low]
    for i in range(1, len(candles)):
        trs.append(true_range(candles[i], candles[i-1]))
    # Wilder's smoothing
    out: List[float] = []
    a = sum(trs[:period]) / period
    # pad leading
    for i in range(period-1):
        out.append(a)
    out.append(a)
    for tr in trs[period:]:
        a = (a*(period-1) + tr) / period
        out.append(a)
    # ensure length
    if len(out) < len(candles):
        out += [out[-1]] * (len(candles) - len(out))
    return out[:len(candles)]

@dataclass
class Trade:
    side: str  # LONG/SHORT
    entry_ts: int
    entry: float
    stop: float
    tp: float
    exit_ts: int = 0
    exit: float = 0.0
    reason: str = ""
    r_mult: float = 0.0

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/btcusdt_5m.csv")
    ap.add_argument("--outdir", default="reports")
    ap.add_argument("--ema", type=int, default=50)
    ap.add_argument("--donchian", type=int, default=20)
    ap.add_argument("--atr", type=int, default=14)
    ap.add_argument("--atr-stop", type=float, default=1.2)
    ap.add_argument("--atr-tp", type=float, default=2.0)
    ap.add_argument("--breakout-buffer-atr", type=float, default=0.2)
    ap.add_argument("--fee-bps", type=float, default=6.0, help="roundtrip fee basis points (paper approx)")
    args = ap.parse_args()

    candles = read_candles(args.inp)
    if len(candles) < max(args.ema, args.donchian, args.atr) + 5:
        raise SystemExit("Not enough candles. Run collect_candles.py longer to build dataset.")

    closes = [c.close for c in candles]
    e = ema(closes, args.ema)
    a = atr(candles, args.atr)

    trades: List[Trade] = []
    pos: Optional[Trade] = None

    def fee(price: float) -> float:
        return price * (args.fee_bps / 10000.0)

    start = max(args.donchian, args.ema, args.atr, 4)
    for i in range(start, len(candles)-1):
        c = candles[i]
        nxt = candles[i+1]
        lookback = candles[i-args.donchian:i]
        if not lookback:
            continue
        hh = max(x.high for x in lookback)
        ll = min(x.low for x in lookback)

        trend_up = c.close > e[i] and e[i] >= e[i-3]
        trend_dn = c.close < e[i] and e[i] <= e[i-3]
        buf = args.breakout_buffer_atr * a[i]

        if pos is None:
            # enter on next candle open after breakout confirmation at close
            if trend_up and c.close > (hh + buf):
                entry = nxt.open + fee(nxt.open)
                stop = entry - args.atr_stop * a[i]
                tp   = entry + args.atr_tp   * a[i]
                pos = Trade("LONG", entry_ts=nxt.ts, entry=entry, stop=stop, tp=tp)
            elif trend_dn and c.close < (ll - buf):
                entry = nxt.open - fee(nxt.open)
                stop = entry + args.atr_stop * a[i]
                tp   = entry - args.atr_tp   * a[i]
                pos = Trade("SHORT", entry_ts=nxt.ts, entry=entry, stop=stop, tp=tp)
        else:
            # manage exits on current candle (assume stop/tp can be hit intrabar)
            if pos.side == "LONG":
                hit_stop = c.low <= pos.stop
                hit_tp   = c.high >= pos.tp
                if hit_stop or hit_tp:
                    exit_price = pos.stop if hit_stop else pos.tp
                    exit_price -= fee(exit_price)
                    pos.exit_ts = c.ts
                    pos.exit = exit_price
                    pos.reason = "STOP" if hit_stop else "TP"
                    risk = pos.entry - pos.stop
                    pos.r_mult = (pos.exit - pos.entry) / risk if risk > 0 else 0.0
                    trades.append(pos)
                    pos = None
            else:
                hit_stop = c.high >= pos.stop
                hit_tp   = c.low <= pos.tp
                if hit_stop or hit_tp:
                    exit_price = pos.stop if hit_stop else pos.tp
                    exit_price += fee(exit_price)
                    pos.exit_ts = c.ts
                    pos.exit = exit_price
                    pos.reason = "STOP" if hit_stop else "TP"
                    risk = pos.stop - pos.entry
                    pos.r_mult = (pos.entry - pos.exit) / risk if risk > 0 else 0.0
                    trades.append(pos)
                    pos = None

    os.makedirs(args.outdir, exist_ok=True)
    trades_csv = os.path.join(args.outdir, "trades_breakout_ema_atr.csv")
    with open(trades_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["side","entry_ts","entry","stop","tp","exit_ts","exit","reason","r_mult"])
        for t in trades:
            w.writerow([t.side,t.entry_ts,round(t.entry,2),round(t.stop,2),round(t.tp,2),t.exit_ts,round(t.exit,2),t.reason,round(t.r_mult,3)])

    total = len(trades)
    wins = sum(1 for t in trades if t.reason == "TP")
    avg_r = sum(t.r_mult for t in trades)/total if total else 0.0
    win_rate = wins/total if total else 0.0
    report = {
        "strategy": "EMA50 + Donchian20 breakout + ATR stops/tp",
        "candles": len(candles),
        "trades": total,
        "win_rate": win_rate,
        "avg_R": avg_r,
        "sum_R": sum(t.r_mult for t in trades),
        "params": vars(args),
        "files": {"trades_csv": trades_csv},
    }
    rep_json = os.path.join(args.outdir, "report_breakout_ema_atr.json")
    with open(rep_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
