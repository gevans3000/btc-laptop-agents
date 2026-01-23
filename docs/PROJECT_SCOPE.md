# BTC Laptop Agents — Project Scope & Requirements Document

> **Version**: 1.2.0
> **Status**: Active
> **Last Updated**: January 2026

## 1. System Overview
**BTC Laptop Agents** is a local-first, privacy-focused trading system. It operates on a "Hardware Ceiling" philosophy where safety limits are hard-coded into the application constants.

## 6. Technical Architecture

### 6.1 Module Structure (Updated)

```text
src/laptop_agents/
├── agents/               # Modular Agent Pipeline
│   ├── supervisor.py     # Pipeline Orchestrator
│   ├── market_intake.py  # Data & Context
│   ├── setup_signal.py   # Strategy Logic
│   ├── execution_risk.py # R:R & Sizing
│   ├── risk_gate.py      # Final Safety Check
│   └── ...
├── commands/             # CLI Handlers (session, backtest, system)
├── core/                 # Infrastructure
│   ├── cases.py          # Domain Entities
│   └── orchestrator.py   # Session Runners
├── data/
│   └── providers/
│       └── bitunix_futures.py  # Unified REST + WS Client
├── constants.py          # Hard Limits & Global Config
└── main.py               # Typer CLI Entry
```

### 6.2 Data Flows
**Consolidated Provider**:
The `BitunixFuturesProvider` now manages a background `BitunixWebsocketClient` thread. This ensures that `get_latest_candle()` returns the most up-to-date market state by merging REST history with the latest WebSocket candle tick.

## 9. Safety & Risk Management

### 9.1 Constants & Hard Limits
Defined in `src/laptop_agents/constants.py`. These parameters serve as the immutable laws of the system.
- `MAX_POSITION_SIZE_USD`: $500.00
- `MAX_DAILY_LOSS_USD`: $50.00
- `MAX_LEVERAGE`: 1.0x (Paper Mode Default)

## 12. Constraints
- **Single Symbol**: Designed to focus on one pair (BTCUSDT) per process.
- **Linear Execution**: Agents run sequentially within the `Supervisor.step()` loop to ensure deterministic state transitions.
- **Offline Agents**: `planner.py` and `researcher.py` are reserved for future LLM-based extensions and are not part of the active hot-loop.
