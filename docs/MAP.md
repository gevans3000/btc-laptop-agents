# MAP.md — Landmark Map

> **PURPOSE**: Quick navigation for the `btc-laptop-agents` codebase. Use this to find logic without scanning the entire project.

## 1. Modular Architecture Overview

Our architecture has transitioned from a monolithic `run.py` to a modular system.

| Logic Area | Location | Primary Function(s) |
| :--- | :--- | :--- |
| **CLI Entry** | `src/laptop_agents/run.py` | Command-line interface wrapper. |
| **Orchestrator** | `src/laptop_agents/core/orchestrator.py` | Main coordination logic (`run_orchestrated_mode`). |
| **Data Loader** | `src/laptop_agents/data/loader.py` | Candle fetching. |
| **Timed Session** | `src/laptop_agents/session/timed_session.py` | Autonomous polling loop for live sessions. |
| **Live Broker** | `src/laptop_agents/execution/bitunix_broker.py` | Real-money execution with Bitunix. |
| **Bitunix Provider** | `src/laptop_agents/data/providers/bitunix_futures.py` | API client for Bitunix Futures. |
| **Paper Broker** | `src/laptop_agents/paper/broker.py` | Simulated execution for backtesting. |
| **Backtest Engine** | `src/laptop_agents/backtest/engine.py` | Historical simulation. |
| **Modular Agents** | `src/laptop_agents/agents/` | Strategy signals and state management. |
| **Resilience** | `src/laptop_agents/resilience/` | Circuit breakers, retries, error handling. |
| **Trading Engine** | `src/laptop_agents/trading/exec_engine.py` | Core trading loop logic. |
| **Hard Limits** | `src/laptop_agents/core/hard_limits.py` | Immutable safety constraints. |

## 2. Script Control Surface

| Script | Purpose | Code Link |
| :--- | :--- | :--- |
| `scripts/verify.ps1` | System health check | Logic in `run.py` and `validation.py` |
| `scripts/test_dual_mode.py` | Logic parity check | Compares Bar vs Position mode math |
| `watchdog.ps1` | Background daemon | Calls `run.py --mode live` |

## 3. Key Data Constants

- **Event Loop Paths**: `RUNS_DIR`, `LATEST_DIR`, `PAPER_DIR` (in `src/laptop_agents/core/orchestrator.py`)
- **Schemas**: `REQUIRED_EVENT_KEYS`, `REQUIRED_TRADE_COLUMNS` (in `src/laptop_agents/tools/validation.py`)

## 4. Live Trading System

| Component | Location | Purpose |
| :--- | :--- | :--- |
| **Readiness Check** | `scripts/check_live_ready.py` | Verify API credentials and connectivity. |
| **Live Session** | `--mode live-session --execution-mode live` | Run autonomous trading session. |
| **Kill Switch** | `config/KILL_SWITCH.txt` | Set content to `TRUE` to halt all trading. |
| **Shutdown** | `BitunixBroker.shutdown()` | Emergency cancel all orders + close positions. |

---
*Note: This map is updated as refactoring phases complete. Phase E (Live Trading & Deployment) is current.*
