from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import csv
import json
from datetime import datetime


@dataclass
class TradeRow:
    trade_id: str
    created_at: str
    setup: str
    direction: str
    entry: Optional[float]
    exit_price: Optional[float]
    r: Optional[float]
    pnl: Optional[float]
    bars_open: Optional[int]
    reason: str


def load_events(journal_path: str) -> List[Dict[str, Any]]:
    p = Path(journal_path)
    if not p.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def summarize(journal_path: str) -> Tuple[Dict[str, Any], List[TradeRow]]:
    events = load_events(journal_path)
    trades: Dict[str, Dict[str, Any]] = {}

    for e in events:
        t = e.get("type")
        tid = e.get("trade_id")
        if not tid:
            continue

        if t == "trade":
            plan = e.get("plan") or {}
            setup = ((plan.get("setup") or {}).get("name")) or "UNKNOWN"
            trades[tid] = {
                "trade": e,
                "setup": setup,
                "fills": [],
                "exits": [],
                "cancels": [],
            }
        elif t == "update" and tid in trades:
            note = e.get("note")
            if note == "fill":
                trades[tid]["fills"].append(e.get("fill") or {})
            elif note == "exit":
                trades[tid]["exits"].append(e.get("exit") or {})
            elif note == "canceled":
                trades[tid]["cancels"].append(e.get("cancel") or {})

    rows: List[TradeRow] = []
    r_list: List[float] = []
    setup_counts: Dict[str, int] = {}
    setup_r: Dict[str, List[float]] = {}

    for tid, obj in trades.items():
        trade = obj["trade"]
        created_at = trade.get("created_at", "")
        direction = trade.get("direction", "")
        setup = obj.get("setup", "UNKNOWN")

        setup_counts[setup] = setup_counts.get(setup, 0) + 1

        fill = obj["fills"][-1] if obj["fills"] else None
        exit_ev = obj["exits"][-1] if obj["exits"] else None
        cancel_ev = obj["cancels"][-1] if obj["cancels"] else None

        entry = float(fill["price"]) if fill and "price" in fill else None
        exit_price = float(exit_ev["price"]) if exit_ev and "price" in exit_ev else None
        r = float(exit_ev["r"]) if exit_ev and "r" in exit_ev else None
        pnl = float(exit_ev["pnl"]) if exit_ev and "pnl" in exit_ev else None
        bars = int(exit_ev["bars_open"]) if exit_ev and "bars_open" in exit_ev else None

        reason = "OPEN_OR_PLANNED"
        if exit_ev:
            reason = str(exit_ev.get("reason", "EXIT"))
        elif cancel_ev:
            reason = f"CANCELED:{cancel_ev.get('reason')}"

        if r is not None:
            r_list.append(r)
            setup_r.setdefault(setup, []).append(r)

        rows.append(
            TradeRow(
                trade_id=tid,
                created_at=created_at,
                setup=setup,
                direction=direction,
                entry=entry,
                exit_price=exit_price,
                r=r,
                pnl=pnl,
                bars_open=bars,
                reason=reason,
            )
        )

    # Metrics (only closed trades with r)
    closed = [x for x in rows if x.r is not None]
    wins = [x for x in closed if (x.r or 0) > 0]
    losses = [x for x in closed if (x.r or 0) <= 0]

    total_r = sum((x.r or 0) for x in closed)
    avg_r = (total_r / len(closed)) if closed else 0.0
    winrate = (len(wins) / len(closed)) if closed else 0.0
    pf = (
        (sum((x.r or 0) for x in wins) / abs(sum((x.r or 0) for x in losses)))
        if losses
        else float("inf")
    )

    # Max drawdown on cumulative R
    peak = 0.0
    eq = 0.0
    max_dd = 0.0
    for x in closed:
        eq += x.r or 0
        peak = max(peak, eq)
        max_dd = min(max_dd, eq - peak)  # negative number

    summary = {
        "journal": journal_path,
        "planned_trades": len(rows),
        "closed_trades": len(closed),
        "winrate": winrate,
        "avg_r": avg_r,
        "total_r": total_r,
        "profit_factor_r": pf,
        "max_drawdown_r": max_dd,
        "setups": {
            k: {
                "planned": setup_counts.get(k, 0),
                "avg_r": (sum(v) / len(v) if v else None),
                "n_closed": len(v),
            }
            for k, v in setup_r.items()
        },
    }
    return summary, rows


def write_report(journal_path: str, out_dir: str = "data/reports") -> Dict[str, str]:
    outp = Path(out_dir)
    outp.mkdir(parents=True, exist_ok=True)

    summary, rows = summarize(journal_path)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    md_path = outp / f"report_{ts}.md"
    csv_path = outp / f"trades_{ts}.csv"

    # markdown
    lines: List[str] = []
    lines.append(f"# BTC Laptop Agents Report ({ts})")
    lines.append("")
    lines.append(f"- Journal: `{journal_path}`")
    lines.append(f"- Planned trades: {summary['planned_trades']}")
    lines.append(f"- Closed trades: {summary['closed_trades']}")
    lines.append(f"- Winrate: {summary['winrate']:.2%}")
    lines.append(f"- Avg R: {summary['avg_r']:.3f}")
    lines.append(f"- Total R: {summary['total_r']:.3f}")
    lines.append(
        f"- Profit factor (R): {summary['profit_factor_r']:.3f}"
        if summary["profit_factor_r"] != float("inf")
        else "- Profit factor (R): inf"
    )
    lines.append(f"- Max drawdown (R): {summary['max_drawdown_r']:.3f}")
    lines.append("")
    lines.append("## Setup breakdown")
    if summary["setups"]:
        for k, v in summary["setups"].items():
            lines.append(
                f"- **{k}**: planned={v['planned']} closed={v['n_closed']} avg_r={(v['avg_r'] if v['avg_r'] is not None else 'n/a')}"
            )
    else:
        lines.append("- (no closed trades yet)")
    lines.append("")
    lines.append("## Notes")
    lines.append("- Closed trades are those with an `exit` event (R realized).")
    lines.append("- Planned-only trades (no fill/exit) are excluded from winrate/avgR.")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # csv
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "trade_id",
                "created_at",
                "setup",
                "direction",
                "entry",
                "exit_price",
                "r",
                "pnl",
                "bars_open",
                "reason",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.trade_id,
                    r.created_at,
                    r.setup,
                    r.direction,
                    r.entry,
                    r.exit_price,
                    r.r,
                    r.pnl,
                    r.bars_open,
                    r.reason,
                ]
            )

    return {"md": str(md_path), "csv": str(csv_path)}
