# ENGINEER.md — The Integrated Operations & Specification Manual

> **Status**: ACTIVE & AUTHORITATIVE
> **Version**: 1.2.0 (Consolidated Architecture)

This document is the **Single Source of Truth** for the BTC Laptop Agents system. It integrates the operational runbook, technical specifications, agent architecture, and API reference.

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
| Action | Command | Description |
| :--- | :--- | :--- |
| **Verify System** | `la doctor --fix` | Runs diagnostics and fixes common issues. |
| **Live Session** | `la run --mode live-session` | Starts autonomous trading loop. |
| **Backtest** | `la backtest --days 2` | Runs historical simulation. |
| **Monitor** | `la status` | Checks process health and heartbeat. |
| **Supervisor**| `la watch` | wrapper ensuring auto-restart on crash. |

### C. Configuration & Safety
**Hard Limits** are defined in `src/laptop_agents/constants.py` and CANNOT be overridden by config files.

| Config File | Purpose |
|------|---------|
| `config/strategies/default.json` | Base strategy logic |
| `src/laptop_agents/constants.py` | **Immutable Safety Limits** (Max Loss, Max Pos) |
| `.workspace/runs/<id>/` | Artifacts (HTML reports, CSV logs) |

---

## 2. Operational Modes

### A. Live Session (Autonomous)
The standard mode for running the agent against real-time data (Paper or Real).
```bash
la run --mode live-session --symbol BTCUSDT --duration 10 --async
```

### B. Backtesting
Dedicated command for historical validation.
```bash
la backtest --symbol BTCUSDT --days 5 --risk-pct 1.0
```

---

## 3. Architecture & Agents

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

### Data Invariants
- **Warmup**: System requires **51 candles** minimum to initialize indicators.
- **Provider**: `BitunixFuturesProvider` handles **BOTH** REST (History) and WebSocket (Real-time) data.

---

## 4. Resilience & Safety

### A. Hard Limits (`constants.py`)
| Limit | Value | Enforcement |
| :--- | :--- | :--- |
| `MAX_POSITION_SIZE_USD` | $500.00 | Rejected at `RiskGateAgent` |
| `MAX_DAILY_LOSS_USD` | $50.00 | Session Kill Switch |
| `MAX_ERRORS_PER_SESSION` | 20 | Process Exit |

### B. Failure Modes
- **Zombie Connection**: WebSocket checks for "Pong" every 60s. If failed, it reconnects.
- **Circuit Breaker**: 5 consecutive losses trip the `ErrorCircuitBreaker`, halting new entries.

---

## 5. Artifacts
Every run produces:
- `summary.html`: Interactive performance dashboard.
- `trades.csv`: Row-by-row trade log.
- `events.jsonl`: Machine-readable event stream (NDJSON).
- `equity.csv`: Time-series equity curve.
