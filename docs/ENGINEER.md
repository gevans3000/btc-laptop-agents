# ENGINEER.md — The Integrated Operations & Specification Manual

> **Status**: ACTIVE & AUTHORITATIVE
> **Version**: 1.1.0 (Cleaned & Consolidated)

This document is the **Single Source of Truth** for the BTC Laptop Agents system. It integrates the operational runbook, technical specifications, agent architecture, and API reference.

---

## Table of Contents
1. [System Overview & Invariants](#1-system-overview--invariants)
2. [Quick Start](#2-quick-start)
   - [A. Environment Setup & Prerequisites](#a-environment-setup--prerequisites)
   - [B. Standard Commands](#b-standard-commands)
3. [Configuration Formats & Precedence](#3-configuration-formats--precedence)
4. [Architecture & Agents](#4-architecture--agents)
5. [Resilience & Safety](#5-resilience--safety)
6. [Troubleshooting](#6-troubleshooting)
7. [State Persistence](#7-state-persistence)

---

## 1. System Overview & Invariants

**BTC Laptop Agents** is a privacy-first, local-first autonomous trading system. It operates on a "Hardware Ceiling" philosophy where safety limits are hard-coded into the application.

### Repo Invariants
- **Local-First**: No external dependencies for core logic execution. Artifacts live in `.workspace/`.
- **Deterministic**: Replaying specific input data must yield identical state transitions.
- **Single Symbol**: Designed to focus on one pair (default `BTCUSDT`) per session.
- **Linear Execution**: Agents run sequentially within the `Supervisor.step()` loop.

---

## 2. Quick Start

### A. Environment Setup & Prerequisites

#### Prerequisites
- **OS**: Windows (tested on Lenovo/Surface hardware).
- **Python**: 3.11 or higher.
- **Git**: For version control.
- **PowerShell**: For running automated scripts (`.ps1`).

#### Installation
1.  **Clone & Install**:
    ```powershell
    pip install -e .
    ```
2.  **Configuration**: Create a `.env` file at the root:
  ```env
  BITUNIX_API_KEY=your_key
  BITUNIX_API_SECRET=your_secret
  ```

### B. Standard Commands
| Action | Command | Description |
| :--- | :--- | :--- |
| **Verify System** | `la doctor --fix` | Runs diagnostics and fixes common issues. |
| **Live Session** | `la run --mode live-session` | Starts autonomous trading loop. |
| **Backtest** | `la backtest --days 2` | Runs historical simulation. |
| **Monitor** | `la status` | Checks process health and heartbeat. |
| **Supervisor**| `la watch` | Wrapper ensuring auto-restart on crash. |

For the full run-time flag list, use `la run --help`.

---

## 3. Configuration Formats & Precedence

### A. Config Files
- **Session config**: JSON file passed via `--config` (see `SessionConfig` in `src/laptop_agents/core/config.py`).
- **Strategy config**: JSON in `config/strategies/<name>.json` loaded via `--strategy`.
- **Risk/exchange config**: YAML in `config/risk.yaml` and `config/exchanges/bitunix.yaml`.

### B. Precedence (Session Config)
Environment variables (`LA_*`) > session config JSON (`--config`) > strategy defaults (`config/strategies/*.json`) > built-in defaults.

---

## 4. Architecture & Agents

The system uses a **MODULAR PIPELINE** managed by `src/laptop_agents/agents/supervisor.py`.

### Active Agent Pipeline (Order of Execution)
1.  **MarketIntakeAgent**: Normalizes candles and computes volatility (ATR).
2.  **DerivativesFlowsAgent**: Checks Funding Rates & Open Interest.
3.  **TrendFilterAgent**: Determines market regime (Trending vs Ranging).
4.  **CvdDivergenceAgent**: Detects Order Flow divergences.
5.  **SetupSignalAgent**: Generates trade setups (Pullback, Sweep).
6.  **ExecutionRiskSentinelAgent**: Sizes positions based on risk % and Stop Loss.
7.  **RiskGateAgent**: Final hard-limit check before execution.
8.  **JournalCoachAgent**: Logs trade lifecycle and manages state interaction.

### Data Flow
- **Consolidated Provider**: `BitunixFuturesProvider` handles **BOTH** REST (History) and WebSocket (Real-time) data.
- **Warmup**: System requires **51 candles** minimum to initialize indicators.

---

## 5. Resilience & Safety

### A. Hard Limits (`constants.py`)
These are immutable laws. They can only be changed by editing the source code.

| Limit | Value | Enforcement |
| :--- | :--- | :--- |
| `MAX_POSITION_SIZE_USD` | $200,000.00 | Rejected at `RiskGateAgent` |
| `MAX_DAILY_LOSS_USD` | $50.00 | Session Kill Switch |
| `MAX_ERRORS_PER_SESSION` | 20 | Process Exit |

### B. Failure Modes
- **Zombie Connection**: WebSocket checks for "Pong" every 60s. If failed, it reconnects.
- **Circuit Breaker**: 5 consecutive losses trip the `ErrorCircuitBreaker`, halting new entries.

---

## 6. Troubleshooting

### Automated Diagnostics
Run `la doctor --fix` to auto-detect and fix Python version, `.env` issues, and permissions.

### Common Issues
| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| **Circuit Breaker Open** | Max consecutive losses (5) or daily drawdown hit. | Review `.workspace/logs/`. Restarting session resets memory, but daily limits persist. |
| **LowCandleCountWarning** | Cold start; not enough history for indicators. | Ensure stable internet for initial history fetch. |
| **Zombie Connection** | WebSocket stopped receiving data. | System auto-reconnects after 60s. No action needed. |
| **Config Validation Error** | Strategy config exceeds hard limits. | Adjust config to be stricter than `constants.py`. |

For historical issues and automated fixes, see the [Known Issues Database](troubleshooting/known_issues.md).

---

## 7. State Persistence (Source of Truth)

- **Unified session state**: `.workspace/paper/unified_state.json` (circuit breaker state, starting equity, supervisor state).
- **Paper broker state (source of truth)**: `.workspace/paper/broker_state.db` (SQLite WAL). A best-effort JSON snapshot is written alongside as `broker_state.json`.
- **Logs/artifacts**: `.workspace/` (see runs, logs, and reports).
