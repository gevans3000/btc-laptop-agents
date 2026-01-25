"""
HTML Dashboard Renderer - Extracted from run.py for compute optimization.

This module contains the render_html function and its HTML template,
which generates the summary.html dashboard for backtest/live results.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

# These will be passed in or imported lazily
_append_event = None
_LATEST_DIR = None


def set_context(latest_dir: Path, append_event_fn: Any) -> None:
    """Set the module context for directory and event logging."""
    global _append_event, _LATEST_DIR
    _LATEST_DIR = latest_dir
    _append_event = append_event_fn


def _safe_append_event(data: Dict[str, Any]) -> None:
    """Safely append an event, falling back to no-op if not set."""
    if _append_event:
        _append_event(data)


def render_html(
    summary: Dict[str, Any],
    trades: List[Dict[str, Any]],
    error_message: str = "",
    candles: List[Any] | None = None,
    latest_dir: Path | None = None,
    append_event_fn: Any = None,
) -> None:
    """
    Render an HTML summary dashboard for backtest/live trading results.

    Args:
        summary: Dict with run metadata (run_id, symbol, interval, balances, etc.)
        trades: List of trade dictionaries
        error_message: Optional error message to display
        candles: Optional list of Candle objects for chart
        latest_dir: Path to the latest runs directory
        append_event_fn: Function to log events
    """
    # Use passed-in or module-level context
    LATEST_DIR = latest_dir or _LATEST_DIR
    append_event = append_event_fn or _append_event or (lambda x: None)

    if LATEST_DIR is None:
        raise ValueError(
            "LATEST_DIR must be set via set_context() or passed to render_html()"
        )

    events_tail = ""
    ep = LATEST_DIR / "events.jsonl"
    if ep.exists():
        events_tail = "\n".join(ep.read_text(encoding="utf-8").splitlines()[-80:])

    rows = ""
    # Show last 10 trades (newest first)
    display_trades = trades[-10:] if len(trades) > 10 else trades
    for t in display_trades:
        pnl = float(t.get("pnl", 0.0))
        pnl_color = "#2f9e44" if pnl >= 0 else "#e03131"
        side = t.get("side", "N/A")
        side_badge = f"<span class='badge badge-{side.lower()}'>{side}</span>"

        trade_id = str(t.get("trade_id") or t.get("exchange_id") or "N/A")
        trade_id_short = trade_id[:8] + "..." if len(trade_id) > 8 else trade_id

        entry_px = float(t.get("entry") or t.get("price", 0.0))
        exit_px = float(t.get("exit") or t.get("price", 0.0))
        quantity = float(t.get("quantity") or t.get("qty", 0.0))
        fees = float(t.get("fees", 0.0))
        timestamp = t.get("timestamp") or t.get("at") or "N/A"

        rows += (
            f"<tr>"
            f"<td class='text-left'><code>{trade_id_short}</code></td>"
            f"<td class='text-center'>{side_badge}</td>"
            f"<td class='text-right'>${entry_px:.2f}</td>"
            f"<td class='text-right'>${exit_px:.2f}</td>"
            f"<td class='text-right'>{quantity:.4f}</td>"
            f"<td class='text-right' style='color: {pnl_color}; font-weight: 600;'>${pnl:.2f}</td>"
            f"<td class='text-right'>${fees:.2f}</td>"
            f"<td class='text-right text-muted'>{timestamp}</td>"
            f"</tr>"
        )
    if not rows:
        rows = "<tr><td colspan='8' class='text-center text-muted'>No trades executed</td></tr>"

    # Error section if there was an error
    error_section = ""
    if error_message:
        error_section = f"""
    <div style="background: #ffebee; border: 1px solid #ef9a9a; padding: 15px; margin: 20px 0; border-radius: 4px;">
        <h3 style="color: #c62828; margin-top: 0;">Error</h3>
        <pre style="margin: 0; white-space: pre-wrap;">{error_message}</pre>
    </div>
"""

    # Prepare data for Plotly
    candle_json = "[]"
    if candles:
        candle_list = []
        for c in candles:
            candle_list.append(
                {
                    "t": str(c.ts),
                    "o": float(c.open),
                    "h": float(c.high),
                    "l": float(c.low),
                    "c": float(c.close),
                }
            )
        candle_json = json.dumps(candle_list)

    trades_json = json.dumps(trades)

    equity_json = "[]"
    equity_csv = LATEST_DIR / "equity.csv"
    if equity_csv.exists():
        try:
            equity_data = []
            with equity_csv.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Support both old "t"/"v" and new "ts"/"equity" formats
                    ts_val = row.get("ts") or row.get("t")
                    equity_val = float(row.get("equity") or row.get("v") or 0.0)
                    equity_data.append({"t": ts_val, "v": equity_val})
            equity_json = json.dumps(equity_data)
        except Exception as e:
            append_event({"event": "EquityDataError", "message": str(e)})

    # Backtest stats section (if available)
    backtest_stats_section = ""
    live_stats_section = ""
    stats_json_path = LATEST_DIR / "stats.json"
    if stats_json_path.exists():
        try:
            with stats_json_path.open("r", encoding="utf-8") as f:
                stats = json.load(f)
                win_rate_pct = stats.get("win_rate", 0.0) * 100
                max_drawdown_pct = stats.get("max_drawdown", 0.0) * 100

                backtest_stats_section = f"""
    <div class="section">
        <h2>Backtest Statistics</h2>
        <div class="cards">
            <div class="card">
                <div class="card-label">Total Trades</div>
                <div class="card-value">{stats.get("trades", 0)}</div>
            </div>
            <div class="card">
                <div class="card-label">Wins</div>
                <div class="card-value">{stats.get("wins", 0)}</div>
            </div>
            <div class="card">
                <div class="card-label">Losses</div>
                <div class="card-value">{stats.get("losses", 0)}</div>
            </div>
            <div class="card">
                <div class="card-label">Win Rate</div>
                <div class="card-value">{win_rate_pct:.1f}%</div>
            </div>
            <div class="card">
                <div class="card-label">Max Drawdown</div>
                <div class="card-value" style="color: #e74c3c;">{max_drawdown_pct:.2f}%</div>
            </div>
            <div class="card">
                <div class="card-label">Sharpe Ratio</div>
                <div class="card-value">{stats.get("sharpe", 0.0):.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">Total Fees</div>
                <div class="card-value">${stats.get("fees_total", 0.0):.2f}</div>
            </div>
        </div>
    </div>
"""
        except Exception as e:
            append_event({"event": "StatsReadError", "message": str(e)})

    if summary.get("mode") == "orchestrated" or summary.get("mode") == "live":
        # Extract current setup/order from summary if available
        setup = summary.get("setup", {})
        setup_name = setup.get("name", "NONE")
        setup_side = setup.get("side", "FLAT")
        setup_info = f"{setup_name} ({setup_side})"

        live_stats_section = f"""
    <div class="section">
        <h2>Modular Agent State</h2>
        <div class="cards">
            <div class="card">
                <div class="card-label">Current Setup</div>
                <div class="card-value">{setup_info}</div>
            </div>
            <div class="card">
                <div class="card-label">Realized PnL</div>
                <div class="card-value">${summary.get("net_pnl", 0.0):.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">Trade Count</div>
                <div class="card-value">{summary.get("trades", 0)}</div>
            </div>
            <div class="card">
                <div class="card-label">Max Drawdown</div>
                <div class="card-value" style="color: #e74c3c;">{summary.get("max_drawdown", 0.0) * 100:.2f}%</div>
            </div>
            <div class="card">
                <span class="stat-value">{summary.get("symbol", "N/A")}</span>
                <span class="stat-value">{summary.get("mode", "N/A")}</span>
            </div>
        </div>
    </div>
"""
    # Validation mode section (if available)
    validation_section = ""
    validation_json_path = LATEST_DIR / "validation.json"
    if validation_json_path.exists():
        try:
            with validation_json_path.open("r", encoding="utf-8") as f:
                validate_data = json.load(f)

            # Top cards with best parameters
            best_params = validate_data.get("best_params", {})
            best_params_card = ""
            if best_params:
                best_params_card = f"""
    <div class="card">
        <div class="card-label">Best Parameters</div>
        <div class="card-value" style="font-size: 0.9em;">
            SMA: {best_params.get("fast_sma", "N/A")},{best_params.get("slow_sma", "N/A")}<br>
            Stop: {best_params.get("stop_bps", "N/A")} bps<br>
            TP: {best_params.get("tp_r", "N/A")}
        </div>
    </div>
"""

            # Leaderboard table (top 10)
            leaderboard_rows = ""
            for entry in validate_data.get("leaderboard", [])[:10]:
                leaderboard_rows += f"""
    <tr>
        <td>{entry.get("rank", "N/A")}</td>
        <td>{entry.get("fast_sma", "N/A")},{entry.get("slow_sma", "N/A")}</td>
        <td>{entry.get("stop_bps", "N/A")}</td>
        <td>{entry.get("tp_r", "N/A")}</td>
        <td>${entry.get("net_pnl", 0):.2f}</td>
        <td>{entry.get("max_drawdown", 0):.2%}</td>
        <td>{entry.get("win_rate", 0):.2%}</td>
        <td>{entry.get("trades", 0)}</td>
        <td>${entry.get("fees_total", 0):.2f}</td>
        <td>{entry.get("objective", 0):.2f}</td>
    </tr>
"""

            # Main validation section
            validation_section = f"""
    <div class="section">
        <h2>Validation Results</h2>
        <div class="cards">
            <div class="card">
                <div class="card-label">Out-of-Sample Net PnL</div>
                <div class="card-value">${validate_data.get("total_os_pnl", 0):.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">Avg Fold PnL</div>
                <div class="card-value">${validate_data.get("avg_os_pnl", 0):.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">Win Rate</div>
                <div class="card-value">{validate_data.get("win_rate", 0):.2%}</div>
            </div>
            <div class="card">
                <div class="card-label">Profit Factor</div>
                <div class="card-value">{validate_data.get("profit_factor", 0):.2f}</div>
            </div>
            {best_params_card}
            <div class="card">
                <div class="card-label">Candles Required</div>
                <div class="card-value" style="font-size: 0.9em;">
                    {validate_data.get("candle_requirements", {}).get("required", "N/A")} required<br>
                    {validate_data.get("candle_requirements", {}).get("actual", "N/A")} actual
                </div>
            </div>
            <div class="card">
                <div class="card-label">Grid Combinations</div>
                <div class="card-value" style="font-size: 0.9em;">
                    {validate_data.get("grid_parsed", {}).get("total_combinations", 0)} total<br>
                    Top 10 shown
                </div>
            </div>
        </div>

        <h3 style="margin-top: 30px;">Leaderboard (Top 10)</h3>
        <table>
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>SMA</th>
                    <th>Stop (bps)</th>
                    <th>TP Ratio</th>
                    <th>Net PnL</th>
                    <th>Max DD</th>
                    <th>Win Rate</th>
                    <th>Trades</th>
                    <th>Fees</th>
                    <th>Objective</th>
                </tr>
            </thead>
            <tbody>{leaderboard_rows}</tbody>
        </table>
    </div>
"""
        except Exception as e:
            append_event({"event": "ValidationRenderError", "message": str(e)})

    # Risk settings cards
    risk_settings_section = ""
    if summary.get("mode") in ["live", "backtest", "orchestrated"]:
        risk_settings_section = f"""
    <div class="section">
        <h2>Risk Settings</h2>
        <div class="cards">
            <div class="card">
                <div class="card-label">Risk %</div>
                <div class="card-value">{summary.get("risk_pct", 1.0)}%</div>
            </div>
            <div class="card">
                <div class="card-label">Stop (bps)</div>
                <div class="card-value">{summary.get("stop_bps", 30.0)} bps</div>
            </div>
            <div class="card">
                <div class="card-label">TP Ratio</div>
                <div class="card-value">{summary.get("tp_r", 1.5)}</div>
            </div>
            <div class="card">
                <div class="card-label">Max Leverage</div>
                <div class="card-value">{summary.get("max_leverage", 1.0)}x</div>
            </div>
            <div class="card">
                <div class="card-label">Intrabar Mode</div>
                <div class="card-value">{summary.get("intrabar_mode", "conservative")}</div>
            </div>
        </div>
    </div>
"""

    # Open position details
    open_position_section = ""
    if summary.get("mode") == "live" and summary.get("position"):
        position = summary["position"]
        open_position_section = f"""
    <div class="section">
        <h2>Open Position</h2>
        <div class="cards">
            <div class="card">
                <div class="card-label">Side</div>
                <div class="card-value">{position["side"]}</div>
            </div>
            <div class="card">
                <div class="card-label">Entry</div>
                <div class="card-value">${position["entry_price"]:.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">Stop</div>
                <div class="card-value">${position["stop_price"]:.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">TP</div>
                <div class="card-value">${position["tp_price"]:.2f}</div>
            </div>
            <div class="card">
                <div class="card-label">Quantity</div>
                <div class="card-value">{position["quantity"]:.8f}</div>
            </div>
        </div>
    </div>
"""

    html = _generate_html_template(
        summary=summary,
        rows=rows,
        error_section=error_section,
        candle_json=candle_json,
        trades_json=trades_json,
        equity_json=equity_json,
        backtest_stats_section=backtest_stats_section,
        live_stats_section=live_stats_section,
        validation_section=validation_section,
        risk_settings_section=risk_settings_section,
        open_position_section=open_position_section,
        events_tail=events_tail,
    )

    # Write to LATEST_DIR for validation/access
    try:
        (LATEST_DIR / "summary.html").write_text(html, encoding="utf-8")
    except Exception as e:
        append_event({"event": "HtmlWriteError", "message": str(e)})


def _generate_html_template(
    summary: Dict[str, Any],
    rows: str,
    error_section: str,
    candle_json: str,
    trades_json: str,
    equity_json: str,
    backtest_stats_section: str,
    live_stats_section: str,
    validation_section: str,
    risk_settings_section: str,
    open_position_section: str,
    events_tail: str,
) -> str:
    """Generate the complete HTML template with all sections."""

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Run Summary - {summary.get("run_id", "")[:8]}</title>
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.5;
      color: #1a1a1a;
      max-width: 1400px;
      margin: 0 auto;
      padding: 40px 20px;
      background-color: #f8f9fa;
    }}
    h1, h2, h3 {{ color: #1a1a1a; font-weight: 700; margin-top: 0; }}
    .section {{
      background: white;
      border: 1px solid #e1e8ed;
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 14px;
      margin-bottom: 24px;
    }}
    .card {{ background: #fdfdfd; border: 1px solid #eee; border-radius: 8px; padding: 16px; }}
    .card-label {{
      font-size: 11px;
      color: #666;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      font-weight: 600;
      margin-bottom: 4px;
    }}
    .card-value {{ font-size: 20px; font-weight: 700; color: #111; }}
    table {{
      border-collapse: collapse;
      width: 100%;
      font-size: 13px;
      overflow: hidden;
      border-radius: 8px;
    }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #eee; }}
    th {{
      background: #f8f9fa;
      font-weight: 600;
      color: #495057;
      text-transform: uppercase;
      font-size: 11px;
      letter-spacing: 0.5px;
    }}
    tr:last-child td {{ border-bottom: none; }}
    tr:hover {{ background: #f8f9fa; }}
    .text-left {{ text-align: left; }}
    .text-right {{ text-align: right; }}
    .text-center {{ text-align: center; }}
    .text-muted {{ color: #868e96; font-size: 12px; }}
    .badge {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    .badge-long {{ background: #d3f9d8; color: #2b8a3e; }}
    .badge-short {{ background: #ffe3e3; color: #c92a2a; }}
    code {{
      background: #f1f3f5;
      padding: 2px 6px;
      border-radius: 3px;
      font-size: 11px;
      font-family: 'Courier New', monospace;
    }}
    .chart-container {{ height: 600px; width: 100%; }}
    .status-badge {{
      display: inline-block;
      padding: 4px 12px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
    }}
    .status-live {{ background: #fff5f5; color: #e03131; border: 1px solid #ffc9c9; }}
    .status-backtest {{ background: #f8f9fa; color: #495057; border: 1px solid #dee2e6; }}
    pre {{ background: #1a1a1a; color: #f8f9fa; padding: 16px; border-radius: 8px; font-size: 12px; overflow-x: auto; }}
  </style>
</head>
<body>
  <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 32px;">
    <div>
      <h1 style="margin-bottom: 4px;">Run Summary</h1>
      <div style="color: #666; font-size: 14px;">Run ID: {summary.get("run_id")} | {summary.get("timestamp")}</div>
    </div>
    <div class="status-badge status-{summary.get("mode", "backtest")}">
      {summary.get("mode", "backtest").upper()} MODE
    </div>
  </div>

  {error_section}

  <div class="section">
    <div class="cards">
      <div class="card"><div class="card-label">Symbol</div><div class="card-value">{summary["symbol"]}</div></div>
      <div class="card"><div class="card-label">Interval</div><div class="card-value">{summary["interval"]}</div></div>
      <div class="card"><div class="card-label">Source</div><div class="card-value">{summary["source"]}</div></div>
      <div class="card">
        <div class="card-label">Starting</div>
        <div class="card-value">${summary["starting_balance"]:.2f}</div>
      </div>
      <div class="card">
        <div class="card-label">Ending</div>
        <div
          class="card-value"
          style="color: {"#2f9e44" if summary["ending_balance"] >= summary["starting_balance"] else "#e03131"}"
        >
          ${summary["ending_balance"]:.2f}
        </div>
      </div>
      <div class="card"><div class="card-label">Net PnL</div>
        <div class="card-value" style="color: {"#2f9e44" if summary["net_pnl"] >= 0 else "#e03131"}">
          ${summary["net_pnl"]:.2f}
        </div>
      </div>
    </div>

    <div id="main-chart" class="chart-container"></div>
  </div>

  <div class="section">
    <h2>Performance Curve</h2>
    <div style="height: 300px; width: 100%;">
      <canvas id="equityCanvas"></canvas>
    </div>
  </div>

  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 24px;">
    {risk_settings_section}
    {backtest_stats_section}
  </div>

  {open_position_section}
  {validation_section}
  {live_stats_section}

  <div class="section">
    <h2>Last 10 Trades</h2>
    <table>
      <thead>
        <tr>
          <th class='text-left'>ID</th>
          <th class='text-center'>Side</th>
          <th class='text-right'>Entry</th>
          <th class='text-right'>Exit</th>
          <th class='text-right'>Qty</th>
          <th class='text-right'>PnL</th>
          <th class='text-right'>Fees</th>
          <th class='text-right'>Time</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

  <div class="section">
    <details>
      <summary style="cursor: pointer; font-weight: 600;">System Logs (Tail)</summary>
      <pre>{events_tail}</pre>
    </details>
  </div>

  <script>
    const candles = {candle_json};
    const trades = {trades_json};
    const equity = {equity_json};

    if (candles.length > 0) {{
        const traceCandles = {{
            x: candles.map(c => c.t),
            close: candles.map(c => c.c),
            high: candles.map(c => c.h),
            low: candles.map(c => c.l),
            open: candles.map(c => c.o),
            type: 'candlestick',
            name: 'Price',
            xaxis: 'x',
            yaxis: 'y'
        }};

        const buyMarkers = {{
            x: trades.filter(t => t.side === 'LONG').map(t => t.timestamp),
            y: trades.filter(t => t.side === 'LONG').map(t => t.entry),
            mode: 'markers',
            type: 'scatter',
            name: 'Buy',
            marker: {{ symbol: 'triangle-up', size: 12, color: '#2f9e44' }},
            xaxis: 'x',
            yaxis: 'y'
        }};

        const sellMarkers = {{
            x: trades.filter(t => t.side === 'SHORT').map(t => t.timestamp),
            y: trades.filter(t => t.side === 'SHORT').map(t => t.entry),
            mode: 'markers',
            type: 'scatter',
            name: 'Sell',
            marker: {{ symbol: 'triangle-down', size: 12, color: '#e03131' }},
            xaxis: 'x',
            yaxis: 'y'
        }};

        const traceEquity = {{
            x: equity.map(e => e.t),
            y: equity.map(e => e.v),
            type: 'scatter',
            name: 'Equity',
            line: {{ color: '#339af0', width: 2 }},
            xaxis: 'x',
            yaxis: 'y2'
        }};

        const layout = {{
            dragmode: 'zoom',
            showlegend: true,
            margin: {{ t: 30, b: 30, l: 60, r: 60 }},
            grid: {{ rows: 2, columns: 1, roworder: 'top to bottom' }},
            xaxis: {{ rangeslider: {{ visible: false }}, type: 'date' }},
            yaxis: {{ title: 'Price', domain: [0.4, 1] }},
            yaxis2: {{ title: 'Equity', domain: [0, 0.3], anchor: 'x' }},
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
        }};

        Plotly.newPlot('main-chart', [traceEquity], layout, {{ responsive: true }});
    }}

    // Chart.js Equity Chart Integration
    if (equity.length > 0) {{
        const ctx = document.getElementById('equityCanvas').getContext('2d');
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: equity.map(e => e.t),
                datasets: [{{
                    label: 'Equity ($)',
                    data: equity.map(e => e.v),
                    borderColor: '#339af0',
                    backgroundColor: 'rgba(51, 154, 240, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.1,
                    pointRadius: 0
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: false,
                        grid: {{ color: 'rgba(0,0,0,0.05)' }}
                    }},
                    x: {{
                        display: false
                    }}
                }}
            }}
        }});
    }}
  </script>
</body>
</html>
"""
