# MAP.md — Landmark Map

> **PURPOSE**: Quick navigation for the `btc-laptop-agents` codebase. Use this to find logic without scanning the entire project.

## 1. Modular Architecture Overview

Our architecture has transitioned from a monolithic `run.py` to a modular system.

| Logic Area | Location | Primary Function(s) |
| :--- | :--- | :--- |
| **CLI Entry** | `src/laptop_agents/run.py` | Command-line interface wrapper. |
| **Orchestrator** | `src/laptop_agents/core/orchestrator.py` | Main coordination logic (`run_orchestrated_mode`). |
| **Data Loader** | `src/laptop_agents/data/loader.py` | Candle fetching (`load_mock_candles`, `load_bitunix_candles`). |
| **Live Loop** | `src/laptop_agents/trading/exec_engine.py` | `run_live_paper_trading` (The main daemon loop). |
| **Backtest Engine** | `src/laptop_agents/backtest/engine.py` | `run_backtest_bar_mode`, `run_backtest_position_mode`, `run_validation`. |
| **Modular Agents** | `src/laptop_agents/agents/` | `Supervisor`, `AgentState`, and strategy setup signals. |
| **Trading Math** | `src/laptop_agents/trading/helpers.py` | `calculate_position_size`, `simulate_trade_one_bar`, `sma` |
| **HTML Renderer** | `src/laptop_agents/reporting/html_renderer.py` | Dashboard generation logic. |
| **Validation** | `src/laptop_agents/tools/validation.py` | `validate_events_jsonl`, `validate_trades_csv`, `validate_summary_html` |
| **Resilience** | `src/laptop_agents/resilience/` | Circuit breakers, retries, and error handling. |
| **Core** | `src/laptop_agents/core/` | Logger, registry, and hard limits. |

## 2. Script Control Surface

| Script | Purpose | Code Link |
| :--- | :--- | :--- |
| `scripts/verify.ps1` | System health check | Logic in `run.py` and `validation.py` |
| `scripts/test_dual_mode.py` | Logic parity check | Compares Bar vs Position mode math |
| `watchdog.ps1` | Background daemon | Calls `run.py --mode live` |

## 3. Key Data Constants

- **Event Loop Paths**: `RUNS_DIR`, `LATEST_DIR`, `PAPER_DIR` (in `src/laptop_agents/core/orchestrator.py`)
- **Schemas**: `REQUIRED_EVENT_KEYS`, `REQUIRED_TRADE_COLUMNS` (in `src/laptop_agents/tools/validation.py`)

---
*Note: This map is updated as refactoring phases complete. Phase D (Modularization & Stabilization) is current.*
