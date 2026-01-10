# MVP_SPEC.md — The "Law" of v1

> **STATUS**: DEPRECATED - See `docs/SPEC.md`
> **SCOPE**: Mirrors `src/laptop_agents/run.py` and `/scripts/` exactly.

This document defines the **current, supported** behavior of the BTC Laptop Agents MVP. Any deviation between this file and the code is a **bug**.

## 1. Canonical Entrypoint

The single source of truth for execution is the python module:
`python -m src.laptop_agents.run`

## 2. Supported Modes

These modes are covered by `verify.ps1` and are considered stable.

| Mode | Flag | Default Source | Description |
| :--- | :--- | :--- | :--- |
| **Single** | *default* | `mock` | Runs a single trade simulation on provided candles. |
| **Backtest** | `--mode backtest` | `mock` | Runs historical backtest (default: position mode). |
| **Live** | `--mode live` | `mock` | Runs the continuous paper trading loop (Daemon). |
| **SelfTest** | `--mode selftest` | *n/a* | Runs deterministic risk engine verification. |

### Experimental Modes (Use with Caution)

| Mode | Flag | Status | Note |
| :--- | :--- | :--- | :--- |
| **Orchestrated** | `--mode orchestrated` | *Beta* | Runs a single E2E cycle with artifact validation. |
| **Validate** | `--mode validate` | *Alpha* | Walk-forward validation with parameter grid. |

## 3. Data Sources & Configuration

| Source | Flag | Auth Required? | Notes |
| :--- | :--- | :--- | :--- |
| **Mock** | `--source mock` | **NO** | Default. Generates synthetic sine-wave market data. |
| **Bitunix** | `--source bitunix` | **OPTIONAL** | API Key/Secret in `.env` **only** if using private endpoints. Public candle data works without keys. |

**External Requirements:**
*   `.venv` (Python 3.12+)
*   `.env` (Optional, for Bitunix private features)

## 4. Canonical Outputs (Artifacts)

The system guarantees the generation of these files in `runs/latest/` (for run-once/backtest) or `paper/` (for live):

### A. Event Log (`events.jsonl`)
*   **Format**: JSON Lines, append-only.
*   **Required Fields**: `timestamp`, `event`.
*   **Guaranteed Events**: `RunStarted`, `MarketDataLoaded`, `RunFinished`.

### B. Trade Log (`trades.csv`)
*   **Format**: CSV standard.
*   **Columns**: `trade_id, side, signal, entry, exit, quantity, pnl, fees, timestamp`.

### C. Dashboard (`summary.html`)
*   **Format**: Standalone HTML.
*   **Content**: Metrics cards, Equity Chart, Trade Table, Events Tail.

### D. State (Live Mode Only)
*   `paper/mvp.pid`: Process ID (existence = running).
*   `paper/state.json`: Persistent state (positions, balance).

## 5. Canonical Scripts (The Control Surface)

These 6 scripts in `/scripts/` are the **only** supported way to operate the system.

1.  `verify.ps1`: Comprehensive system health check.
2.  `mvp_start_live.ps1`: Starts the background daemon.
3.  `mvp_stop_live.ps1`: Safely stops the daemon.
4.  `mvp_status.ps1`: Checks PID and recent logs.
5.  `mvp_run_once.ps1`: runs `mode=single` (verification).
6.  `mvp_open.ps1`: Opens `summary.html`.
