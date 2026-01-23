from __future__ import annotations

import json
import time
import csv
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from laptop_agents.core.logger import logger, write_alert
from laptop_agents.core.orchestrator import LATEST_DIR, render_html

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


def export_metrics(runner: "AsyncRunner") -> None:
    """Exports session metrics to JSON and CSV."""
    try:
        metrics_path = LATEST_DIR / "metrics.json"
        with open(metrics_path, "w") as f:
            json.dump(runner.metrics, f, indent=2)
        logger.info(f"Metrics exported to {metrics_path}")
    except Exception as me:
        logger.error(f"Failed to export metrics: {me}")

    try:
        csv_path = LATEST_DIR / "metrics.csv"
        if runner.metrics:
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=runner.metrics[0].keys())
                writer.writeheader()
                writer.writerows(runner.metrics)
            logger.info(f"Metrics exported to {csv_path}")
    except Exception as ce:
        logger.error(f"Failed to export CSV metrics: {ce}")


def generate_final_reports(runner: "AsyncRunner") -> None:
    """Generates summary.json, final_report.json, and CLI text summary."""
    # 4.3 Session Summary Report
    try:
        from laptop_agents.reporting.summary import generate_summary

        summary = generate_summary(runner.broker, runner.start_time)
        summary_path = LATEST_DIR / "summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Session summary written to {summary_path}")
    except Exception as se:
        logger.error(f"Failed to generate summary: {se}")

    # Generate final_report.json
    try:
        report_path = LATEST_DIR / "final_report.json"
        exit_code = 0 if runner.errors == 0 else 1
        report = {
            "status": "success" if exit_code == 0 else "error",
            "exit_code": exit_code,
            "pnl_absolute": round(
                runner.broker.current_equity - runner.starting_equity, 2
            ),
            "error_count": runner.errors,
            "duration_seconds": round(time.time() - runner.start_time, 1),
            "symbol": runner.symbol,
            "trades": runner.trades,
            "stopped_reason": runner.stopped_reason,
        }
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Final report written to {report_path}")

        # Post-Run Performance Summary (CLI)
        trades_list = [
            h for h in runner.broker.order_history if h.get("type") == "exit"
        ]
        wins = [t for t in trades_list if t.get("pnl", 0) > 0]
        win_rate = (len(wins) / len(trades_list) * 100) if trades_list else 0.0
        total_fees = sum(t.get("fees", 0) for t in trades_list)
        net_pnl = float(runner.broker.current_equity - runner.starting_equity)
        pnl_pct = (
            (net_pnl / runner.starting_equity * 100)
            if runner.starting_equity > 0
            else 0.0
        )

        summary_text = f"""
========== SESSION COMPLETE (ASYNC) ==========
Symbol:     {runner.symbol}
Start:      ${runner.starting_equity:,.2f}
End:        ${runner.broker.current_equity:,.2f}
Net PnL:    ${net_pnl:,.2f} ({pnl_pct:+.2f}%)
--------------------------------------
Trades:     {len(trades_list)}
Win Rate:   {win_rate:.1f}%
Total Fees: ${total_fees:,.2f}
==============================================
"""
        logger.info(summary_text)
    except Exception as re:
        logger.error(f"CRITICAL: Failed to write final report/summary: {re}")

    if runner.errors > 0:
        write_alert(f"Session failed with {runner.errors} errors")


def generate_html_report(runner: "AsyncRunner", starting_balance: float) -> None:
    """Generates the main HTML report."""
    try:
        LATEST_DIR.mkdir(parents=True, exist_ok=True)
        summary_source = "bitunix"
        if runner.strategy_config:
            summary_source = runner.strategy_config.get("source") or summary_source

        summary = {
            "run_id": f"async_{int(runner.start_time)}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": summary_source,
            "symbol": runner.symbol,
            "interval": runner.interval,
            "candle_count": len(runner.candles),
            "last_ts": runner.candles[-1].ts if runner.candles else "",
            "last_close": (float(runner.candles[-1].close) if runner.candles else 0.0),
            "fees_bps": getattr(runner.broker, "fees_bps", 0.0),  # Safer access
            "slip_bps": getattr(runner.broker, "slip_bps", 0.0),  # Safer access
            "starting_balance": starting_balance,
            "ending_balance": runner.broker.current_equity,
            "net_pnl": runner.broker.current_equity - starting_balance,
            "max_drawdown": runner.max_drawdown,
            "trades": runner.trades,
            "mode": "async",
        }
        # Pass trades from broker history for a complete report
        trades_for_report = [
            h for h in runner.broker.order_history if h.get("type") == "exit"
        ]
        render_html(
            summary,
            trades_for_report,
            "",
            candles=runner.candles,
        )
        logger.info(f"HTML report generated at {LATEST_DIR / 'summary.html'}")
    except Exception as e:
        logger.error(f"Failed to generate HTML report: {e}")
