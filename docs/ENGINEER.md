# ENGINEER.md — The Integrated Operations & Specification Manual

> **Status**: ACTIVE & AUTHORITATIVE
> **Version**: 1.1.0 (Structural Polish)

This document is the **Single Source of Truth** for the BTC Laptop Agents system. It integrates the operational runbook, technical specifications, agent architecture, and API reference.

---

## Table of Contents
1. [Quick Start](#1-quick-start)
2. [System Specification](#2-system-specification)
3. [Operational Modes](#3-operational-modes)
4. [Architecture & Agents](#4-architecture--agents)
5. [API Reference](#5-api-reference)
6. [Resilience & Safety](#6-resilience--safety)
7. [Logs & Artifacts](#7-logs--artifacts)

---

## 1. Quick Start

### A. Environment Setup
- **Python**: 3.10 or higher.
- **Installation**: `pip install -e .`
- **Configuration**: Create a `.env` file at the root:
  ```env
  BITUNIX_API_KEY=your_key
  BITUNIX_API_SECRET=your_secret
  ```

### B. Standard Commands
| Action | Command |
| :--- | :--- |
| **Verify System** | `la doctor --fix` |
| **Start Session** | `la start --mode live-session --duration 10` |
| **Monitor** | `la status` |
| **Stop** | `la stop` |
| **Watch/Supervise**| `la watch --mode live-session --duration 10` |

---

## 2. System Specification

BTC Laptop Agents is a local-first, privacy-focused trading system designed to run on a standard laptop. 

### Core Principles
1.  **Safety First**: Hard-coded risk limits cannot be overridden.
2.  **Determinism**: Replaying a run with the same data must yield the same result.
3.  **Artifact-Driven**: Every stage produced verifiable JSON/CSV artifacts.

### Interface & Modes
The canonical entrypoint is `la` (or `python -m laptop_agents`).

| Mode | CLI Argument | Description |
| :--- | :--- | :--- |
| **Verify** | `la doctor` | Runs environment and connection checks. |
| **Backtest** | `la run --mode backtest` | Simulates trading over historical data. |
| **Live Session** | `la run --mode live-session` | Autonomous loop for timed trading. |
| **Watch** | `la watch` | Process supervisor for auto-restart. |

---

## 3. Operational Modes

### A. Live Session (Autonomous)
The standard mode for running the agent for a fixed duration.
```bash
la run --mode live-session --symbol BTCUSD --duration 10 --async
```

### B. Backtesting
Run historical simulations to test strategy performance.
```bash
la run --mode backtest --backtest 500 --risk-pct 1.0
```
- `--backtest-mode`: `position` (default) or `bar`.
- `--intrabar-mode`: `conservative` (stop first) or `optimistic`.

---

## 4. Architecture & Agents

The system uses a **MODULAR PIPELINE** in orchestrated modes.

### Active Modular Agents
- **MarketIntakeAgent**: Data normalization.
- **SetupSignalAgent**: Trend Ribbon + Sweep logic.
- **ExecutionRiskSentinelAgent**: Risk sizing & safety gates.
- **JournalCoachAgent**: Trade logging.

### Critical Invariants
- **Candle Integrity**: Data must be chronological.
- **Risk Invariant**: Max risk 1.0% per trade, REQUIRED stop loss.

---

## 5. API Reference

### Brokers
- `PaperBroker`: Simulated fills for backtesting and paper trading.
- `BitunixBroker`: Real-money orders for Bitunix Futures. Includes `shutdown()` to cancel all orders and close positions.

### Providers
- `BitunixFuturesProvider`: API client for Bitunix (Klines, Orders, Positions).

---

## 6. Resilience & Safety

### A. Process Watchdog (`la watch`)
The supervisor monitors the trading process and restarts it if it crashes.
- **Delay**: 10 seconds between restarts.
- **Log**: `.workspace/logs/supervisor.log`.

### B. Failsafes
- **Kill Switch**: Create `config/KILL_SWITCH.txt` with `TRUE` to halt all orders.
- **Daily Loss**: Hard-coded limit of $50 USD.
- **Max Position**: $200,000 USD.

---

## 7. Logs & Artifacts

All runs generate artifacts in `.workspace/runs/<id>/`.

- `summary.html`: Interactive dashboard.
- `trades.csv`: Detailed trade log.
- `events.jsonl`: Machine-readable event stream.
- `system.jsonl`: Global system logs/errors.
