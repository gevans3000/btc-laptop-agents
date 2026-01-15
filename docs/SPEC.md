# BTC Laptop Agents — System Specification

> **Status**: ACTIVE & AUTHORITATIVE
> **Version**: 1.0.1 (Resilience & Safety)

This document is the **Single Source of Truth** for the BTC Laptop Agents system. It merges the operational details of the MVP with the validation strictness of the Target Contract.

## 1. System Overview

BTC Laptop Agents is a local-first, privacy-focused trading system designed to run on a standard laptop. It has evolved from a monolithic script (`run.py`) to a modular, multi-agent orchestrated pipeline. For day-to-day operations, see [RUNBOOK.md](RUNBOOK.md).

**Core Principles:**
1.  **Safety First**: Hard-coded risk limits cannot be overridden by AI.
2.  **Determinism**: Replaying a run with the same data must yield the exact same result.
3.  **Artifact-Driven**: Every stage of execution produces verifiable JSON/CSV artifacts.

## 2. Interface Prompts & Modes

The canonical entrypoint is `python -m src.laptop_agents.run`.

### Primary Modes (Stable)

| Mode | CLI Argument | Description | Output Artifacts |
| :--- | :--- | :--- | :--- |
| **Verify** | `--mode selftest` | Runs internal risk engine deterministic checks. | `summary.html` (Pass/Fail) |
| **Backtest** | `--mode backtest` | Simulates trading over historical data. | `trades.csv`, `equity.csv` |
| **Live** | `--mode live` | Runs the continuous background daemon. | `paper/state.json`, `paper/mvp.pid` |
| **Live Session** | `--mode live-session` | Autonomous polling loop for timed trading. | `paper/events.jsonl` |
| **Single** | *default* | Single-step simulation (dev/debug). | `events.jsonl` |

### Experimental Modes

| Mode | CLI Argument | Description | Status |
| :--- | :--- | :--- | :--- |
| **Orchestrated** | `--mode orchestrated` | Runs the V2 pipeline with explicit artifact stages. | Beta |
| **Validate** | `--mode validate` | Walk-forward optimization sweep. | Alpha |

## 3. Data Sources

| Source | Flag | Auth? | Description |
| :--- | :--- | :--- | :--- |
| **Mock** | `--source mock` | No | Synthetic sine-wave data for offline dev. |
| **Bitunix** | `--source bitunix` | Optional | Live/Historical market data. API/Secret needed for private endpoints only. |

## 4. Canonical Outputs (The Contract)

Every run MUST generate these artifacts in `runs/<id>/` (or `paper/` for live).

### A. Event Log (`events.jsonl`)
*   **Format**: JSON Lines, append-only.
*   **Schema**:
    ```json
    {"timestamp": "ISO8601", "event": "EventName", "run_id": "uuid", "data": {...}}
    ```
*   **Required Events**: `RunStarted`, `MarketDataLoaded`, `RunFinished`.

### B. Trade Log (`trades.csv`)
*   **Format**: Standard CSV.
*   **Columns**: `trade_id, side, signal, entry, exit, quantity, pnl, fees, timestamp, exit_reason`.

### C. Dashboard (`summary.html`)
*   **Format**: Self-contained HTML file.
*   **Purpose**: Human-readable report with equity curves and metrics.

### D. State (Live Only)
*   **Location**: `paper/` directory.
*   **Files**: `mvp.pid` (Lockfile), `state.json` (Persistence), `live.out.txt` (Logs).

## 5. Verification Gates

The system enforces these invariants (implemented in `src/laptop_agents/run.py`, `src/laptop_agents/trading/exec_engine.py`, and `agents/risk_gate.py`):

1.  **Candle Integrity**: Data must be chronological with no missing timestamps.
2.  **Feature Sanity**: Indicators (SMA/RSI) must be non-NaN before strategy execution.
3.  **Risk Invariant**:
    *   Max Risk per Trade: 1.0% of Equity.
    *   Stop Loss: REQUIRED for every trade.
    *   Risk/Reward: Hard limit 1.0R minimum (code: `hard_limits.MIN_RR_RATIO`); Config default: 1.5R.

## 6. Control Surface (Scripts)

Operators interact via `scripts/` ONLY.

*   `verify.ps1`: System health check.
*   `mvp_start_live.ps1` / `mvp_stop_live.ps1`: Daemon control.
*   `mvp_status.ps1`: Process and log monitoring.
*   `mvp_open.ps1`: Dashboard viewer.

## 7. Live Trading

### Execution Modes
| Mode | Flag | Description |
| :--- | :--- | :--- |
| **Paper** | `--execution-mode paper` | Simulated fills using PaperBroker. |
| **Live** | `--execution-mode live` | Real orders via BitunixBroker. |

### Safety Features
1. **Dynamic Sizing**: Position size is calculated based on risk/config, validated against hard limits.
2. **Human Confirmation**: Orders require manual `y` confirmation unless `SKIP_LIVE_CONFIRM=TRUE`.
3. **Kill Switch**: Create `config/KILL_SWITCH.txt` with `TRUE` to halt all orders.
4. **Graceful Shutdown**: Ctrl+C triggers `shutdown()` which cancels orders and closes positions.

### Quick Start
```powershell
# 1. Verify readiness
$env:PYTHONPATH='src'; python scripts/check_live_ready.py

# 2. Run 10-minute paper session with live data
$env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session --source bitunix --symbol BTCUSD --execution-mode paper --duration 10

# 3. Run live session (REAL MONEY - requires confirmation)
$env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session --source bitunix --symbol BTCUSD --execution-mode live --duration 10
```

## 8. System Requirements

| Requirement | Version | Notes |
| :--- | :--- | :--- |
| **Python** | 3.10+ | Required for match statements and type hints |
| **PowerShell** | 5.0+ | Windows built-in is sufficient |
| **OS** | Windows 10/11 | Primary development target |
| **Dependencies** | See `requirements.txt` | Install via `pip install -r requirements.txt` |

