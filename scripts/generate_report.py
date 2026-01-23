#!/usr/bin/env python
"""Generate PDF-like performance report from run results."""

import json
import csv
from pathlib import Path
from datetime import datetime

RUNS_DIR = Path(__file__).parent.parent / "runs" / "latest"


def generate_report():
    trades_csv = RUNS_DIR / "trades.csv"
    stats_json = RUNS_DIR / "stats.json"

    print("=" * 50)
    print("PERFORMANCE REPORT")
    print(f"Generated: {datetime.now().isoformat()}")
    print("=" * 50)

    if stats_json.exists():
        with stats_json.open() as f:
            stats = json.load(f)
        print(f"Total Trades: {stats.get('trades', 0)}")
        print(f"Win Rate: {stats.get('win_rate', 0) * 100:.1f}%")
        print(f"Max Drawdown: {stats.get('max_drawdown', 0) * 100:.2f}%")

    if trades_csv.exists():
        with trades_csv.open() as f:
            trades = list(csv.DictReader(f))
        total_pnl = sum(float(t.get("pnl", 0)) for t in trades)
        print(f"Total PnL: ${total_pnl:.2f}")
        print(f"Trade Count: {len(trades)}")

    print("=" * 50)


if __name__ == "__main__":
    generate_report()
