# MAP.md — Landmark Map

> **PURPOSE**: Quick navigation for the `src/laptop_agents/run.py` monolith. Use this to find logic without scanning the entire file.

## 1. Core Logic Landmarks (`run.py`)

| Logic Area | Line Range (approx) | Primary Function(s) |
| :--- | :--- | :--- |
| **Validation** | 34 - 104 | `validate_events_jsonl`, `validate_trades_csv`, `validate_summary_html` |
| **Data Sources** | 291 - 327 | `load_mock_candles`, `load_bitunix_candles` |
| **Risk Engine** | 336 - 393 | `calculate_position_size` (The mathematical core) |
| **Grid / Search** | 396 - 1057 | `parse_grid`, `run_validation` (Optimization logic) |
| **Backtest Engine** | 1091 - 1697 | `run_backtest_bar_mode`, `run_backtest_position_mode` |
| **Live Loop** | 1700 - 2107 | `run_live_paper_trading` (The main daemon loop) |
| **Signals** | 2110 - 2120 | `generate_signal` (Where strategy lives) |
| **Execution** | 2123 - 2169 | `simulate_trade_one_bar` (Paper fill logic) |
| **Reporting** | 2202 - 2784 | `render_html` (Dashboard generation) |
| **CLI / Main** | 2787 - 3286 | `main()` (Argument parsing and orchestration) |

## 2. Script Control Surface

| Script | Purpose | Code Link |
| :--- | :--- | :--- |
| `verify.ps1` | System health check | Logic in `run.py` (Validation section) |
| `mvp_start_live.ps1` | Background daemon | Calls `run.py --mode live` |
| `mvp_status.ps1` | Health check / Logs | Checks `paper/` artifacts |

## 3. Dangerous Zones (Read-Only unless asked)

- **Event Loop Timing**: (Lines 1700-1800) The loop interval and exception handling are delicate for daemon stability.
- **Risk Invariants**: (Lines 336-393) Do not change stop/TP math without updating `run_selftest`.
- **CSV/JSON Schema**: (Lines 1-33) Constants defining required columns. Breaking these breaks the dashboard.
