from __future__ import annotations

__all__ = [
    "write_trades_csv",
    "write_state",
    "render_html",
    "print_session_summary",
    "parse_journal_for_trades",
    "finalize_run_reporting",
]

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from laptop_agents.core.logger import logger
from laptop_agents.core.events import (
    append_event,
    LATEST_DIR,
)
from laptop_agents.trading.paper_journal import PaperJournal
from laptop_agents.trading.helpers import Candle


def write_trades_csv(trades: List[Dict[str, Any]]) -> None:
    p = LATEST_DIR / "trades.csv"
    fieldnames = [
        "trade_id",
        "side",
        "signal",
        "entry",
        "exit",
        "price",
        "quantity",
        "pnl",
        "fees",
        "entry_ts",
        "exit_ts",
        "timestamp",
        "setup",
    ]

    temp_p = p.with_suffix(".tmp")
    try:
        with temp_p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for t in trades:
                filtered_trade = {k: v for k, v in t.items() if k in fieldnames}
                w.writerow(filtered_trade)
        temp_p.replace(p)
    except Exception as e:
        if temp_p.exists():
            temp_p.unlink()
        raise RuntimeError(f"Failed to write trades.csv: {e}")


def write_state(state: Dict[str, Any]) -> None:
    with (LATEST_DIR / "state.json").open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def render_html(
    summary: Dict[str, Any],
    trades: List[Dict[str, Any]],
    error_message: str = "",
    candles: List[Candle] | None = None,
) -> None:
    from laptop_agents.reporting.html_renderer import render_html as _render_html

    _render_html(
        summary=summary,
        trades=trades,
        error_message=error_message,
        candles=candles,
        latest_dir=LATEST_DIR,
        append_event_fn=append_event,
    )


def print_session_summary(
    run_id: str, symbol: str, start: float, end: float, trades: List[Dict[str, Any]]
) -> None:
    wins = [t for t in trades if t.get("pnl", 0) > 0]
    wr = (len(wins) / len(trades) * 100) if trades else 0.0
    net = float(end - start)
    pct = (net / start * 100) if start > 0 else 0.0
    logger.info(
        f"\nSESS: {run_id} | {symbol} | Net: ${net:,.2f} ({pct:+.2f}%) | WR: {wr:.1f}%"
    )


def parse_journal_for_trades(journal_path: Path) -> List[Dict[str, Any]]:
    trades: List[Dict[str, Any]] = []
    if journal_path.exists():
        journal = PaperJournal(journal_path)
        open_trades: Dict[str, Any] = {}
        for event in journal.iter_events():
            if event.get("type") == "update":
                tid = event.get("trade_id")
                if tid is None:
                    continue
                if "fill" in event:
                    open_trades[tid] = event["fill"]
                elif "exit" in event and tid in open_trades:
                    f, x = open_trades.pop(tid), event["exit"]
                    trades.append(
                        {
                            "trade_id": tid,
                            "side": f.get("side", "???"),
                            "signal": "MODULAR",
                            "entry": float(f.get("price", 0)),
                            "exit": float(x.get("price", 0)),
                            "quantity": float(f.get("qty", 0)),
                            "pnl": float(x.get("pnl", 0)),
                            "fees": float(f.get("fees", 0)) + float(x.get("fees", 0)),
                            "entry_ts": str(f.get("at", "")),
                            "exit_ts": str(x.get("at", "")),
                            "timestamp": str(x.get("at", event.get("at", ""))),
                            "setup": f.get("setup", "unknown"),
                        }
                    )
    return trades


def finalize_run_reporting(
    run_id: str,
    run_dir: Path,
    candles: List[Candle],
    starting_balance: float,
    ending_balance: float,
    equity_history: List[Dict[str, Any]],
    fees_bps: float,
    slip_bps: float,
    symbol: str,
    interval: str,
    source: str,
    risk_pct: float,
    stop_bps: float,
    tp_r: float,
) -> None:
    # Save equity history
    equity_csv = LATEST_DIR / "equity.csv"
    with equity_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ts", "equity"])
        writer.writeheader()
        writer.writerows(equity_history)

    # Process journal for trades
    trades = parse_journal_for_trades(run_dir / "journal.jsonl")
    write_trades_csv(trades)

    summary = {
        "run_id": run_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "symbol": symbol,
        "interval": interval,
        "candle_count": len(candles),
        "last_ts": str(candles[-1].ts),
        "starting_balance": starting_balance,
        "ending_balance": float(ending_balance),
        "net_pnl": float(ending_balance - starting_balance),
        "trades": len(trades),
        "risk_pct": risk_pct,
        "stop_bps": stop_bps,
        "tp_r": tp_r,
    }
    write_state({"summary": summary})
    render_html(summary, trades, "", candles=candles)

    # Copy artifacts
    for fname in ["trades.csv", "events.jsonl", "summary.html"]:
        if (LATEST_DIR / fname).exists():
            shutil.copy2(LATEST_DIR / fname, run_dir / fname)

    print_session_summary(run_id, symbol, starting_balance, ending_balance, trades)
