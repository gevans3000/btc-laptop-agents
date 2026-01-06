from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------- Paths (anchor to repo root) ----------------
HERE = Path(__file__).resolve()
repo = HERE
for _ in range(10):
    if (repo / "pyproject.toml").exists():
        break
    repo = repo.parent
RUNS_DIR = repo / "runs"
LATEST_DIR = RUNS_DIR / "latest"


def utc_ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def reset_latest_dir() -> None:
    RUNS_DIR.mkdir(exist_ok=True)
    if LATEST_DIR.exists():
        shutil.rmtree(LATEST_DIR)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)


def append_event(obj: Dict[str, Any]) -> None:
    obj.setdefault("timestamp", utc_ts())
    with (LATEST_DIR / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


@dataclass
class Candle:
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def load_mock_candles(n: int = 200) -> List[Candle]:
    candles: List[Candle] = []
    price = 100_000.0
    for i in range(n):
        price += 5.0 + (20.0 if (i % 20) < 10 else -20.0)
        o = price - 10.0
        c = price + 10.0
        h = max(o, c) + 15.0
        l = min(o, c) - 15.0
        candles.append(Candle(ts=f"mock_{i:04d}", open=o, high=h, low=l, close=c, volume=1.0))
    return candles


def _get_bitunix_provider_class():
    import laptop_agents.data.providers.bitunix_futures as m
    for name in dir(m):
        obj = getattr(m, name)
        if isinstance(obj, type) and hasattr(obj, "klines"):
            return obj
    raise RuntimeError("No Bitunix provider class with .klines() found in laptop_agents.data.providers.bitunix_futures")


def load_bitunix_candles(symbol: str, interval: str, limit: int) -> List[Candle]:
    Provider = _get_bitunix_provider_class()
    client = Provider(symbol=symbol)
    rows = client.klines(interval=interval, limit=int(limit))

    out: List[Candle] = []
    for c in rows:
        ts = getattr(c, "ts", None) or getattr(c, "time", None) or getattr(c, "timestamp", None) or ""
        o = float(getattr(c, "open"))
        h = float(getattr(c, "high"))
        l = float(getattr(c, "low"))
        cl = float(getattr(c, "close"))
        v = float(getattr(c, "volume", 0.0) or 0.0)
        out.append(Candle(ts=str(ts), open=o, high=h, low=l, close=cl, volume=v))
    return out


def sma(vals: List[float], window: int) -> Optional[float]:
    if len(vals) < window:
        return None
    return sum(vals[-window:]) / float(window)


def generate_signal(candles: List[Candle]) -> Optional[str]:
    # Avoid lookahead: compute signal on candles[:-1]
    base = candles[:-1]
    if len(base) < 30:
        return None
    closes = [c.close for c in base]
    fast = sma(closes, 10)
    slow = sma(closes, 30)
    if fast is None or slow is None:
        return None
    return "BUY" if fast > slow else "SELL"


def simulate_trade_one_bar(
    *,
    signal: str,
    entry_px: float,
    exit_px: float,
    starting_balance: float,
    fees_bps: float,
    slip_bps: float,
) -> Dict[str, Any]:
    """
    One-trade, one-bar realized PnL:
      - entry at prev close
      - exit at last close
      - slippage applied adversely on both sides
      - fees charged on notional (entry + exit)
    """
    fees_rate = fees_bps / 10_000.0
    slip_rate = slip_bps / 10_000.0

    if signal == "BUY":
        side = "LONG"
        entry = entry_px * (1.0 + slip_rate)
        exit_ = exit_px * (1.0 - slip_rate)
        qty = starting_balance / entry if entry > 0 else 0.0
        gross = (exit_ - entry) * qty
    else:
        side = "SHORT"
        entry = entry_px * (1.0 - slip_rate)
        exit_ = exit_px * (1.0 + slip_rate)
        qty = starting_balance / entry if entry > 0 else 0.0
        gross = (entry - exit_) * qty

    fees = (entry * qty + exit_ * qty) * fees_rate
    pnl = gross - fees

    return {
        "trade_id": str(uuid.uuid4()),
        "side": side,
        "signal": signal,
        "entry": float(entry),
        "exit": float(exit_),
        "price": float(exit_),  # display as last/exit
        "quantity": float(qty),
        "pnl": float(pnl),
        "fees": float(fees),
        "timestamp": utc_ts(),
    }


def write_trades_csv(trades: List[Dict[str, Any]]) -> None:
    p = LATEST_DIR / "trades.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["trade_id", "side", "signal", "entry", "exit", "quantity", "pnl", "fees", "timestamp"],
        )
        w.writeheader()
        for t in trades:
            w.writerow(t)


def write_state(state: Dict[str, Any]) -> None:
    with (LATEST_DIR / "state.json").open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def render_html(summary: Dict[str, Any], trades: List[Dict[str, Any]]) -> None:
    events_tail = ""
    ep = LATEST_DIR / "events.jsonl"
    if ep.exists():
        events_tail = "\n".join(ep.read_text(encoding="utf-8").splitlines()[-80:])

    rows = ""
    for t in trades:
        rows += (
            f"<tr><td>{t['trade_id']}</td><td>{t['side']}</td><td>{t['signal']}</td>"
            f"<td>${float(t['entry']):.2f}</td><td>${float(t['exit']):.2f}</td>"
            f"<td>{float(t['quantity']):.8f}</td><td>${float(t['pnl']):.2f}</td><td>${float(t['fees']):.2f}</td>"
            f"<td>{t['timestamp']}</td></tr>"
        )
    if not rows:
        rows = "<tr><td colspan='10'>No trades</td></tr>"

    html = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Run Summary</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 20px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; }}
    th {{ background: #f6f6f6; text-align: left; }}
    pre {{ background: #f6f6f6; padding: 12px; overflow:auto; }}
    .meta {{ color:#444; margin-bottom: 10px; }}
  </style>
</head>
<body>
  <h1>Run Summary</h1>
  <div class="meta">
    <div><b>Run ID:</b> {summary['run_id']}</div>
    <div><b>Source:</b> {summary['source']} | <b>Symbol:</b> {summary['symbol']} | <b>Interval:</b> {summary['interval']} | <b>Candles:</b> {summary['candle_count']}</div>
    <div><b>Last Candle:</b> ts={summary['last_ts']} close={summary['last_close']}</div>
    <div><b>Fees (bps):</b> {summary['fees_bps']} | <b>Slippage (bps):</b> {summary['slip_bps']}</div>
  </div>

  <p><b>Starting Balance:</b> ${summary['starting_balance']:.2f}</p>
  <p><b>Ending Balance:</b> ${summary['ending_balance']:.2f}</p>
  <p><b>Net PnL:</b> ${summary['net_pnl']:.2f}</p>

  <h2>Trades</h2>
  <table>
    <thead>
      <tr>
        <th>Trade ID</th><th>Side</th><th>Signal</th><th>Entry</th><th>Exit</th>
        <th>Quantity</th><th>PnL</th><th>Fees</th><th>Timestamp</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>

  <h2>Events Tail</h2>
  <pre>{events_tail}</pre>
</body>
</html>
"""
    (LATEST_DIR / "summary.html").write_text(html, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["mock", "bitunix"], default="mock")
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--interval", default="1m")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--fees-bps", type=float, default=2.0)   # 2 bps per side (simple)
    ap.add_argument("--slip-bps", type=float, default=0.5)   # tiny adverse slip
    args = ap.parse_args()

    reset_latest_dir()

    run_id = str(uuid.uuid4())
    starting_balance = 10_000.0

    append_event({"event": "RunStarted", "run_id": run_id, "source": args.source, "symbol": args.symbol, "interval": args.interval})

    try:
        if args.source == "bitunix":
            limit = min(max(int(args.limit), 2), 200)
            candles = load_bitunix_candles(args.symbol, args.interval, limit)
        else:
            candles = load_mock_candles(max(int(args.limit), 50))

        append_event({"event": "MarketDataLoaded", "source": args.source, "symbol": args.symbol, "interval": args.interval, "count": len(candles)})

        if len(candles) < 2:
            raise RuntimeError("Need at least 2 candles to simulate a one-bar trade")

        last = candles[-1]
        prev = candles[-2]
        append_event({"event": "LastCandle", "ts": last.ts, "close": last.close})
        append_event({"event": "PrevCandle", "ts": prev.ts, "close": prev.close})

        signal = generate_signal(candles)
        append_event({"event": "SignalGenerated", "signal": signal})

        trades: List[Dict[str, Any]] = []
        ending_balance = starting_balance

        if signal in ("BUY", "SELL"):
            trade = simulate_trade_one_bar(
                signal=signal,
                entry_px=float(prev.close),
                exit_px=float(last.close),
                starting_balance=starting_balance,
                fees_bps=float(args.fees_bps),
                slip_bps=float(args.slip_bps),
            )
            trades.append(trade)
            ending_balance = starting_balance + float(trade["pnl"])
            append_event({"event": "TradeSimulated", "trade": trade})
        else:
            append_event({"event": "NoTrade", "reason": "insufficient data for SMA(10/30)"})

        write_trades_csv(trades)

        summary = {
            "run_id": run_id,
            "source": args.source,
            "symbol": args.symbol,
            "interval": args.interval,
            "candle_count": len(candles),
            "last_ts": str(last.ts),
            "last_close": float(last.close),
            "fees_bps": float(args.fees_bps),
            "slip_bps": float(args.slip_bps),
            "starting_balance": starting_balance,
            "ending_balance": float(ending_balance),
            "net_pnl": float(ending_balance - starting_balance),
            "trades": len(trades),
        }
        write_state({"summary": summary})
        render_html(summary, trades)

        append_event({"event": "RunFinished", "run_id": run_id})
        return 0

    except Exception as e:
        append_event({"event": "Error", "message": str(e)})
        print("ERROR:", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
