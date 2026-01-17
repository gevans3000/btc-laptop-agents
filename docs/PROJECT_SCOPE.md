# BTC Laptop Agents — Project Scope & Requirements Document

> **Version**: 1.1.0
> **Status**: Complete
> **Last Updated**: January 2026
> **Audience**: Third-party development teams, contractors, or agencies

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Target Users](#3-target-users)
4. [System Overview](#4-system-overview)
5. [Functional Requirements](#5-functional-requirements)
6. [Technical Architecture](#6-technical-architecture)
7. [Data Flows & Storage](#7-data-flows--storage)
8. [Business Logic & Trading Rules](#8-business-logic--trading-rules)
9. [Safety & Risk Management](#9-safety--risk-management)
10. [Non-Functional Requirements](#10-non-functional-requirements)
11. [External Integrations](#11-external-integrations)
12. [Edge Cases & Constraints](#12-edge-cases--constraints)
13. [Testing Requirements](#13-testing-requirements)
14. [Deployment & Operations](#14-deployment--operations)
15. [Appendix: Configuration Schema](#appendix-a-configuration-schema)

---

## 1. Executive Summary

**BTC Laptop Agents** is a **local-first, privacy-focused paper trading and backtesting system** for Bitcoin futures. It is designed to run entirely on a standard laptop without requiring cloud infrastructure, external databases, or third-party analytics services.

### Core Value Proposition

- **Autonomous Trading Simulation**: Execute paper trades against real-time market data using configurable strategies
- **Historical Backtesting**: Test strategies against historical data with realistic fee/slippage modeling
- **Safety-First Design**: Hard-coded risk limits prevent catastrophic losses even during development
- **Deterministic Reproducibility**: Given the same data, runs produce identical results
- **Privacy**: All data stays local; no telemetry or external reporting

### Primary Capabilities

| Capability | Description |
|------------|-------------|
| **Paper Trading** | Simulated order execution with realistic fills, fees, and slippage |
| **Backtesting** | Historical strategy testing with walk-forward validation |
| **Live Sessions** | Timed autonomous trading against real-time WebSocket data |
| **Process Supervision** | Auto-restart on crash with watchdog monitoring |
| **HTML Reporting** | Interactive post-session analysis dashboards |

---

## 2. Problem Statement

### Problems Addressed

1. **Cloud Lock-In**: Most trading bots require cloud servers, creating recurring costs and privacy concerns
2. **Overcomplicated Tooling**: Existing solutions have steep learning curves with excessive configuration
3. **No Safety Guardrails**: Many systems allow users to deploy risky strategies without hard limits
4. **Non-Reproducible Results**: Randomized fills and timing make debugging impossible
5. **Privacy Leakage**: SaaS platforms transmit trading data to external servers

### Solution Approach

- Single CLI entry point (`la`) for all operations
- Hermetic workspace (`.workspace/`) containing all artifacts
- Hard-coded safety limits that cannot be overridden
- Deterministic execution engine with configurable seed
- Zero external dependencies for core functionality

---

## 3. Target Users

### Primary Persona: Retail Algorithmic Trader

- **Technical Level**: Intermediate (comfortable with CLI, Python, JSON)
- **Goal**: Test and refine trading strategies before deploying real capital
- **Environment**: Windows/Linux laptop, intermittent internet
- **Risk Tolerance**: Conservative; wants to validate strategies safely

### Secondary Persona: Quantitative Developer

- **Technical Level**: Advanced
- **Goal**: Build and backtest custom strategies with full control
- **Environment**: Development machine with Python 3.10+
- **Needs**: Extensible agent architecture, detailed event logs

### Use Cases

| ID | Use Case | Actor |
|----|----------|-------|
| UC-1 | Run 10-minute paper trading session against live BTC data | Trader |
| UC-2 | Backtest SMA crossover strategy on 500 historical candles | Trader |
| UC-3 | Validate strategy with walk-forward cross-validation | Quant Dev |
| UC-4 | Monitor session with auto-restart on crash | Trader |
| UC-5 | Review HTML summary of session performance | Trader |
| UC-6 | Add custom signal agent to pipeline | Quant Dev |

---

## 4. System Overview

### 4.1 Unified CLI Interface

All system operations flow through the `la` command (installed via `pip install -e .`).

```
la <command> [options]

Commands:
  run       Start a trading session (foreground)
  start     Start a session in background (detached)
  stop      Stop any running session
  watch     Supervisor with auto-restart
  status    Check system vitals
  doctor    Diagnostic tool
  clean     Remove old artifacts
```

### 4.2 Operational Modes

| Mode | Command | Description |
|------|---------|-------------|
| **Live Session** | `la run --mode live-session --duration 10` | Autonomous trading for N minutes |
| **Backtest** | `la run --mode backtest --backtest 500` | Historical simulation |
| **Validation** | `la run --mode validate --grid "..."` | Walk-forward optimization |
| **Orchestrated** | `la run --mode orchestrated` | Agent pipeline (single tick) |
| **Doctor** | `la doctor --fix` | Environment verification |

### 4.3 High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                              │
│                        (la CLI / Typer)                             │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      SESSION ORCHESTRATOR                           │
│           (AsyncRunner / TimedSession / BacktestEngine)             │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  DATA PROVIDER  │   │  AGENT PIPELINE │   │  PAPER BROKER   │
│  (Bitunix WS)   │   │  (Supervisor)   │   │  (Fill Engine)  │
└─────────────────┘   └─────────────────┘   └─────────────────┘
          │                     │                     │
          └─────────────────────┼─────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      ARTIFACT GENERATION                            │
│        (summary.html, trades.csv, events.jsonl, state.json)         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Functional Requirements

### 5.1 Session Management (FR-100)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-101 | System SHALL start a trading session via `la run` or `la start` | P0 |
| FR-102 | System SHALL stop any running session via `la stop` | P0 |
| FR-103 | System SHALL prevent multiple concurrent sessions via PID locking | P0 |
| FR-104 | System SHALL write PID to `.workspace/agent.pid` on start | P1 |
| FR-105 | System SHALL remove PID file on clean shutdown | P1 |
| FR-106 | `la watch` SHALL restart crashed sessions within 10 seconds | P1 |
| FR-107 | System SHALL log supervisor events to `.workspace/logs/supervisor.log` | P2 |

### 5.2 Data Acquisition (FR-200)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-201 | System SHALL fetch OHLCV candles from Bitunix Futures REST API | P0 |
| FR-202 | System SHALL receive real-time ticks via Bitunix WebSocket | P0 |
| FR-203 | System SHALL support mock data provider for testing | P1 |
| FR-204 | System SHALL seed historical candles (min 100) before live session | P0 |
| FR-205 | System SHALL detect and log candle gaps | P2 |
| FR-206 | Candles SHALL be normalized to chronological order (oldest first) | P0 |

### 5.3 Signal Generation (FR-300)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-301 | System SHALL generate BUY/SELL signals based on SMA crossover | P0 |
| FR-302 | SMA periods SHALL be configurable (default: fast=10, slow=30) | P1 |
| FR-303 | System SHALL filter signals when ATR/Close < 0.5% (low volatility) | P1 |
| FR-304 | SetupSignalAgent SHALL support "pullback_ribbon" setup | P2 |
| FR-305 | SetupSignalAgent SHALL support "sweep_invalidation" setup | P2 |
| FR-306 | Sweep detection SHALL identify high/low sweeps with reclaim | P2 |

### 5.4 Order Execution (FR-400)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-401 | PaperBroker SHALL simulate market orders at bid/ask | P0 |
| FR-402 | PaperBroker SHALL simulate limit orders on price touch | P1 |
| FR-403 | System SHALL apply configurable slippage (basis points) | P0 |
| FR-404 | System SHALL apply configurable trading fees (basis points) | P0 |
| FR-405 | System SHALL support single position only (no pyramiding) | P0 |
| FR-406 | Stop-loss SHALL trigger when price touches stop level | P0 |
| FR-407 | Take-profit SHALL trigger when price touches TP level | P0 |
| FR-408 | When both SL/TP hit in same bar, use intrabar_mode to resolve | P1 |
| FR-409 | System SHALL support trailing stop activation | P2 |
| FR-410 | System SHALL simulate order book impact for large orders | P2 |
| FR-411 | System SHALL cap fill quantity to 10% of candle volume | P2 |

### 5.5 Backtesting (FR-500)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-501 | System SHALL run backtest on N historical candles | P0 |
| FR-502 | Backtest SHALL produce equity curve CSV | P0 |
| FR-503 | Backtest SHALL compute win rate, net PnL, max drawdown | P0 |
| FR-504 | System SHALL support "bar" mode (trade every bar) | P1 |
| FR-505 | System SHALL support "position" mode (hold until exit) | P0 |
| FR-506 | Walk-forward validation SHALL split data into train/test folds | P1 |
| FR-507 | Grid search SHALL test parameter combinations | P1 |
| FR-508 | Validation SHALL cap candidates at 200 to limit compute | P2 |

### 5.6 Reporting (FR-600)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-601 | System SHALL generate `summary.html` after each run | P0 |
| FR-602 | System SHALL write trades to `trades.csv` | P0 |
| FR-603 | System SHALL write events to `events.jsonl` (machine-readable) | P0 |
| FR-604 | HTML report SHALL include equity curve chart | P1 |
| FR-605 | HTML report SHALL include trade table with PnL | P1 |
| FR-606 | `--show` flag SHALL auto-open summary in browser | P2 |

### 5.7 Dashboard (FR-700)

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-701 | `--dashboard` flag SHALL launch local web UI on port 5000 | P2 |
| FR-702 | Dashboard SHALL display real-time equity | P2 |
| FR-703 | Dashboard SHALL display open position status | P2 |

---

## 6. Technical Architecture

### 6.1 Technology Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Language | Python | ≥3.10 |
| CLI Framework | Typer | ≥0.15.4 |
| HTTP Client | httpx | ≥0.28.1 |
| WebSocket Client | websockets | ≥12.0 |
| Data Validation | Pydantic | ≥2.10.2 |
| Terminal UI | Rich | ≥13.9.4 |
| Process Management | psutil | ≥5.9.0 |
| Retry Logic | tenacity | ≥8.5.0 |
| Config | python-dotenv | ≥1.0.1 |

### 6.2 Module Structure

```
src/laptop_agents/
├── __init__.py           # Version export
├── __main__.py           # Entry point
├── main.py               # CLI app definition
├── constants.py          # Global constants
├── indicators.py         # Technical indicators (EMA, ATR, VWAP, CVD)
├── health.py             # Health check utilities
│
├── agents/               # Agent pipeline
│   ├── base.py           # Base agent class
│   ├── supervisor.py     # Pipeline orchestrator
│   ├── market_intake.py  # Data normalization
│   ├── setup_signal.py   # Signal generation
│   ├── execution_risk.py # Risk sizing
│   ├── journal_coach.py  # Trade logging
│   ├── risk_gate.py      # Final safety gate
│   ├── cvd_divergence.py # CVD indicator agent
│   ├── derivatives_flows.py # Funding rate processing
│   ├── trend_filter.py   # Trend classification
│   └── state.py          # Shared state object
│
├── backtest/             # Historical simulation
│   ├── engine.py         # Backtest execution
│   └── replay_runner.py  # Recorded data replay
│
├── commands/             # CLI commands
│   ├── lifecycle.py      # start/stop/watch
│   ├── session.py        # run command
│   └── system.py         # status/doctor/clean
│
├── core/                 # Core infrastructure
│   ├── config.py         # Configuration loading
│   ├── config_models.py  # Pydantic models
│   ├── hard_limits.py    # Safety constants
│   ├── lock_manager.py   # PID locking
│   ├── logger.py         # Structured logging
│   ├── orchestrator.py   # Main orchestration
│   ├── preflight.py      # Pre-run checks
│   ├── rate_limiter.py   # API rate limiting
│   ├── registry.py       # Agent registry
│   ├── runner.py         # Execution runner
│   ├── state_manager.py  # State persistence
│   └── validation.py     # Input validation
│
├── dashboard/            # Web UI
│   ├── app.py            # Flask app
│   └── templates/        # HTML templates
│
├── data/                 # Data layer
│   ├── loader.py         # Data loading utilities
│   └── providers/        # Exchange integrations
│       ├── bitunix_futures.py  # REST client
│       ├── bitunix_ws.py       # WebSocket client
│       ├── mock.py             # Test provider
│       └── composite.py        # Multi-source aggregation
│
├── execution/            # Trade execution
│   └── fees.py           # Fee calculation
│
├── memory/               # State persistence
│
├── paper/                # Paper trading
│   └── broker.py         # Paper broker implementation
│
├── reporting/            # Report generation
│   ├── core.py           # Report utilities
│   └── html_renderer.py  # HTML generation
│
├── resilience/           # Fault tolerance
│   ├── circuit.py        # API circuit breaker
│   ├── errors.py         # Custom exceptions
│   ├── log.py            # Error logging
│   ├── rate_limiter.py   # Rate limiting
│   ├── retry.py          # Retry policies
│   └── trading_circuit_breaker.py  # Equity-based halt
│
├── session/              # Session management
│   ├── async_session.py  # Async event loop
│   └── timed_session.py  # Sync timed session
│
└── trading/              # Trading logic
    ├── exec_engine.py    # Live execution engine
    ├── helpers.py        # Candle, Tick, utilities
    ├── paper_journal.py  # Trade journaling
    └── signal.py         # Signal generation
```

### 6.3 Agent Pipeline Architecture

The system uses a **modular agent pipeline** where each agent transforms shared state:

```
Candle → [MarketIntakeAgent] → [DerivativesFlowsAgent] → [CvdDivergenceAgent]
                                                              ↓
            [JournalCoachAgent] ← [RiskGateAgent] ← [ExecutionRiskAgent] ← [SetupSignalAgent]
                                                              ↓
                                                        [PaperBroker]
```

| Agent | Responsibility |
|-------|----------------|
| **MarketIntakeAgent** | Normalize candle data, compute market context (price, ATR, trend) |
| **DerivativesFlowsAgent** | Fetch funding rate, set trading flags (NO_TRADE, HALF_SIZE) |
| **CvdDivergenceAgent** | Compute CVD divergence for confirmation |
| **SetupSignalAgent** | Identify trading setups (pullback, sweep reclaim) |
| **ExecutionRiskSentinelAgent** | Size position, compute SL/TP, GO/NO-GO decision |
| **RiskGateAgent** | Final hard limit enforcement |
| **JournalCoachAgent** | Log trades, manage trade IDs |
| **PaperBroker** | Execute fills, manage position lifecycle |

---

## 7. Data Flows & Storage

### 7.1 Data Sources

| Source | Type | Data | Refresh Rate |
|--------|------|------|--------------|
| Bitunix REST | HTTP | Historical candles, funding rate | On demand |
| Bitunix WebSocket | WS | Real-time ticks (bid/ask/last) | Continuous |
| Mock Provider | Memory | Synthetic candles | Simulated |

### 7.2 Workspace Structure

All artifacts are stored in `.workspace/` to keep the project root clean:

```
.workspace/
├── agent.pid                 # Current process ID
├── runs/
│   ├── latest/              # Symlink/copy of most recent run
│   │   ├── summary.html     # Interactive report
│   │   ├── trades.csv       # Trade log
│   │   ├── events.jsonl     # Machine-readable events
│   │   ├── equity.csv       # Equity curve
│   │   └── stats.json       # Run statistics
│   └── <run_id>/            # Historical runs
├── logs/
│   ├── system.log           # Application logs
│   └── supervisor.log       # Watchdog logs
└── paper/
    ├── state.json           # Persistent broker state
    ├── async_broker_state.json
    ├── events.jsonl         # Paper trading events
    └── trades.csv           # Paper trade log
```

### 7.3 Configuration Files

```
config/
├── strategies/
│   ├── default.json         # Base strategy config
│   ├── scalp_1m_sweep.json  # Custom strategy
│   └── *.json               # Additional presets
├── live_trading_enabled.txt # Feature flag
└── symbol_overrides.json    # Symbol-specific settings
```

### 7.4 State Persistence

The system maintains state across restarts:

| File | Purpose | Format |
|------|---------|--------|
| `paper/state.json` | Broker position, equity, order history | JSON |
| `paper/async_broker_state.json` | Async session broker state | JSON |
| Circuit breaker state | Tripped status, consecutive losses | In-memory + JSON |

**Atomic Write Pattern**: All state writes use temp file → validate → backup → rename to prevent corruption.

### 7.5 Event Schema

Events are logged to `events.jsonl` in NDJSON format:

```json
{"event": "PositionOpened", "side": "LONG", "price": 45000.0, "qty": 0.1, "ts": "2026-01-17T10:00:00Z"}
{"event": "PositionClosed", "reason": "TP", "price": 45300.0, "pnl": 28.5, "ts": "2026-01-17T10:05:00Z"}
{"event": "HardLimitPositionCapped", "original_qty": 0.5, "capped_qty": 0.2, "limit": 200000}
{"event": "CircuitBreakerTripped", "reason": "max_daily_drawdown", "drawdown_pct": 5.2}
```

---

## 8. Business Logic & Trading Rules

### 8.1 Signal Generation

**Primary Strategy: SMA Crossover**

```
IF SMA(10) > SMA(30) AND volatility_filter_pass:
    signal = BUY
ELSE IF SMA(10) < SMA(30) AND volatility_filter_pass:
    signal = SELL
ELSE:
    signal = HOLD
```

**Volatility Filter**:
```
IF ATR(14) / Close < 0.5%:
    REJECT signal (low volatility)
```

### 8.2 Position Sizing

```python
risk_amount = equity × (risk_pct / 100)
stop_distance = entry_price × (stop_bps / 10000)
qty_raw = risk_amount / stop_distance

# Cap by leverage
max_notional = equity × max_leverage
max_qty = max_notional / entry_price
qty = min(qty_raw, max_qty)

# Cap by hard limits
qty = min(qty, MAX_POSITION_SIZE_USD / entry_price)

# Enforce lot step
qty = floor(qty / lot_step) × lot_step

# Enforce minimum notional
IF qty × entry_price < min_notional:
    REJECT trade
```

### 8.3 Stop-Loss / Take-Profit

**For LONG positions**:
- Stop = Entry - (Entry × stop_bps / 10000)
- TP = Entry + (stop_distance × tp_r_mult)
- Invariant: Stop < Entry < TP

**For SHORT positions**:
- Stop = Entry + (Entry × stop_bps / 10000)
- TP = Entry - (stop_distance × tp_r_mult)
- Invariant: TP < Entry < Stop

### 8.4 Intrabar Resolution

When both SL and TP are hit in the same candle:

| Mode | Behavior |
|------|----------|
| `conservative` | Assume stop hit first (worst case) |
| `optimistic` | Assume TP hit first (best case) |

### 8.5 Funding Rate Gates

| Condition | Action |
|-----------|--------|
| Funding > 5% (8h) | NO_TRADE flag |
| Funding > 3% (8h) | HALF_SIZE flag |
| Funding unavailable | HALF_SIZE flag |

### 8.6 Trade Lifecycle

```
1. SIGNAL generated → SetupSignalAgent
2. ORDER constructed → ExecutionRiskAgent
3. RISK GATE check → RiskGateAgent
4. FILL executed → PaperBroker
5. POSITION monitored → on_candle / on_tick
6. EXIT triggered → SL/TP/Reverse/Force
7. PNL calculated → fees deducted
8. STATE persisted → state.json
```

---

## 9. Safety & Risk Management

### 9.1 Hard Limits (Cannot Be Overridden)

These constants are defined in `core/hard_limits.py` and enforced at multiple layers:

| Limit | Value | Enforcement |
|-------|-------|-------------|
| `MAX_POSITION_SIZE_USD` | $200,000 | Order rejection |
| `MAX_DAILY_LOSS_USD` | $50 | Trading halt |
| `MAX_DAILY_LOSS_PCT` | 5% | Circuit breaker trip |
| `MAX_LEVERAGE` | 20x | Position sizing cap |
| `MIN_RR_RATIO` | 1.0 | Trade rejection |
| `MAX_ORDERS_PER_MINUTE` | 10 | Rate limiting |
| `MAX_ERRORS_PER_SESSION` | 20 | Session shutdown |

### 9.2 Circuit Breaker

The TradingCircuitBreaker monitors equity and halts trading when:

1. **Daily Drawdown** ≥ 5% of starting equity
2. **Consecutive Losses** ≥ 5 trades

**Behavior when tripped**:
- All new orders rejected
- Open positions remain (not force-closed)
- Status logged to events
- Manual reset required or new day resets

### 9.3 Kill Switch

Set environment variable `LA_KILL_SWITCH=TRUE` to:
- Halt all trading immediately
- Prevent new sessions from starting
- Logged as critical event

### 9.4 Process Watchdog

The threaded watchdog (`_threaded_watchdog`) monitors:

| Condition | Action |
|-----------|--------|
| Main loop frozen > 30s | Force process exit (`os._exit(1)`) |
| Memory usage > 1.5 GB | Force process exit |

### 9.5 Rate Limiting

| Scope | Limit |
|-------|-------|
| Orders per minute | 10 |
| API calls per second | 2 (Bitunix) |
| WebSocket reconnect backoff | 5s base, exponential |

---

## 10. Non-Functional Requirements

### 10.1 Performance

| Metric | Target |
|--------|--------|
| Candle processing latency | < 100ms |
| WebSocket message processing | < 50ms |
| State persistence | < 500ms |
| Backtest throughput | > 1000 candles/sec |
| Memory usage (idle) | < 200 MB |
| Memory usage (live session) | < 500 MB |

### 10.2 Reliability

| Requirement | Target |
|-------------|--------|
| Session uptime | 99% (during trading hours) |
| Auto-restart time | < 10 seconds |
| Data loss on crash | None (state persisted) |
| Graceful shutdown | < 5 seconds |

### 10.3 Scalability

| Aspect | Limit |
|--------|-------|
| Concurrent sessions | 1 (by design) |
| Historical candle storage | 800 in memory |
| Trade history | Unlimited (CSV append) |
| Event log | Unlimited (JSONL append) |

### 10.4 Security

| Requirement | Implementation |
|-------------|----------------|
| API key storage | `.env` file (not committed) |
| Secret redaction | `[REDACTED:*]` in logs |
| No telemetry | All data stays local |
| Input validation | Pydantic models |

### 10.5 Usability

| Requirement | Implementation |
|-------------|----------------|
| Single entry point | `la` command |
| Color-coded output | Rich console |
| Progress indicators | For long operations |
| Error messages | Actionable with context |

---

## 11. External Integrations

### 11.1 Bitunix Futures API

**Base URL**: `https://fapi.bitunix.com`

**Endpoints Used**:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/futures/market/kline` | GET | Historical candles |
| `/api/v1/futures/market/funding_rate` | GET | Funding rate |
| `/api/v1/futures/market/tickers` | GET | Current prices |
| `/api/v1/futures/market/trading_pairs` | GET | Instrument info |
| `/api/v1/futures/trade/place_order` | POST | Order placement (live) |
| `/api/v1/futures/trade/cancel_order` | POST | Order cancellation |
| `/api/v1/futures/position/get_pending_positions` | GET | Position query |

**Authentication** (for signed endpoints):
```
digest = SHA256(nonce + timestamp + apiKey + queryParams + body)
sign = SHA256(digest + secretKey)
```

**WebSocket URL**: `wss://fapi.bitunix.com/public`

**Subscriptions**:
- Ticker stream
- Candle/kline stream

### 11.2 Rate Limits

| Type | Limit |
|------|-------|
| REST requests | 10/second |
| WebSocket messages | 100/second |
| Candle fetch (max per request) | 200 |

### 11.3 Other Provider Support (Scaffolded)

The system includes stubs for:
- Binance Futures
- Bybit Derivatives
- OKX Swap
- Kraken Spot

These are not fully implemented but follow the same provider interface.

---

## 12. Edge Cases & Constraints

### 12.1 Edge Cases

| Case | Handling |
|------|----------|
| WebSocket disconnect | Retry with exponential backoff (up to 10 attempts) |
| Stale data (> 30s since last update) | Log warning, continue with last known price |
| Candle gaps in history | Log warning, proceed (may affect indicators) |
| Both SL/TP hit same bar | Use intrabar_mode setting |
| Order rejected by hard limit | Log event, do not enter position |
| Corrupt state file | Load from `.bak`, or start fresh |
| Process killed mid-write | Atomic write pattern prevents corruption |
| Duplicate order IDs | Idempotency check, reject duplicate |
| Zero volume candle | Skip liquidity capping |
| Negative PnL exceeds equity | Circuit breaker trips |

### 12.2 Known Constraints

| Constraint | Reason |
|------------|--------|
| Single position only | Simplicity; no hedge/pyramid logic |
| Single symbol per session | Resource management |
| BTCUSDT default | Most liquid pair |
| 1-minute minimum timeframe | Indicator accuracy |
| Paper trading only by default | Safety-first approach |
| Windows path support | Designed for laptop use |

### 12.3 Assumptions

1. Internet connectivity is available during live sessions
2. User has Python 3.10+ installed
3. Bitunix API remains stable (v1)
4. System clock is reasonably accurate (< 5s drift)
5. Disk space available for logs/artifacts

---

## 13. Testing Requirements

### 13.1 Test Categories

| Category | Location | Purpose |
|----------|----------|---------|
| Unit Tests | `tests/test_*.py` | Component isolation |
| Integration Tests | `tests/test_*_integration.py` | End-to-end flows |
| Smoke Tests | `tests/test_smoke.py` | Basic functionality |
| Regression Tests | `tests/regressions/` | Bug prevention |
| Stress Tests | `tests/stress/` | Performance limits |

### 13.2 Key Test Files

| File | Coverage |
|------|----------|
| `test_broker_state_recovery.py` | State persistence/recovery |
| `test_circuit_breaker.py` | Risk management |
| `test_safety.py` | Hard limit enforcement |
| `test_pipeline_smoke.py` | Agent pipeline |
| `test_sweep_indicators.py` | Technical indicators |
| `test_async_integration.py` | Async session flow |

### 13.3 Test Commands

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest --cov=laptop_agents tests/

# Run specific category
pytest tests/test_safety.py -v
```

---

## 14. Deployment & Operations

### 14.1 Installation

```bash
# Clone repository
git clone https://github.com/gevans3000/btc-laptop-agents.git
cd btc-laptop-agents

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Install in development mode
pip install -e .

# Configure API keys (optional, for live data)
cp .env.example .env
# Edit .env with BITUNIX_API_KEY and BITUNIX_API_SECRET
```

### 14.2 Configuration

```bash
# Verify environment
la doctor --fix

# Check status
la status
```

### 14.3 Running a Session

```bash
# 10-minute paper trading session
la run --mode live-session --duration 10 --source bitunix

# With dashboard
la run --mode live-session --duration 10 --dashboard

# Backtest 500 candles
la run --mode backtest --backtest 500 --source bitunix

# Background with auto-restart
la watch --mode live-session --duration 60
```

### 14.4 Monitoring

```bash
# Check if running
la status

# View logs
Get-Content .workspace\logs\system.log -Tail 50

# View supervisor log
Get-Content .workspace\logs\supervisor.log

# Check events
Get-Content .workspace\paper\events.jsonl -Tail 20
```

### 14.5 Stopping

```bash
# Graceful stop
la stop

# Force stop (if stuck)
taskkill /F /PID <pid>  # Windows
kill -9 <pid>           # Linux
```

---

## Appendix A: Configuration Schema

### Strategy Configuration (`config/strategies/default.json`)

```json
{
    "meta": {
        "name": "Default",
        "author": "System",
        "timeframe": "1m",
        "notes": "Baseline conservative settings."
    },
    "engine": {
        "pending_trigger_max_bars": 24,
        "derivatives_refresh_bars": 6,
        "min_history_bars": 100
    },
    "derivatives_gates": {
        "no_trade_funding_8h": 0.05,
        "half_size_funding_8h": 0.03
    },
    "setups": {
        "pullback_ribbon": {
            "enabled": true,
            "entry_band_pct": 0.001,
            "stop_atr_mult": 1.5,
            "tp_r_mult": 2.0
        },
        "sweep_invalidation": {
            "enabled": true,
            "eq_tolerance_pct": 0.0008,
            "tp_r_mult": 2.0,
            "vwap_target": true,
            "ema_filter": true,
            "ema_period": 200,
            "stop_atr_mult": 0.5,
            "min_vol_ratio": 0.5,
            "lookback_bars": 10,
            "require_cvd_confirm": false
        }
    },
    "risk": {
        "equity": 10000,
        "risk_pct": 1.0,
        "rr_min": 1.5
    },
    "cvd": {
        "lookback": 20,
        "enabled": true
    }
}
```

### Environment Variables (`.env`)

```env
# API Credentials (optional for paper trading)
BITUNIX_API_KEY=your_key
BITUNIX_API_SECRET=your_secret

# Runtime Overrides
LA_SOURCE=mock                # mock | bitunix
LA_SYMBOL=BTCUSDT
LA_INTERVAL=1m
LA_DURATION=10
LA_STRATEGY=default

# Safety
LA_KILL_SWITCH=FALSE          # Set TRUE to halt all trading
```

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2025-12-01 | System | Initial release |
| 1.1.0 | 2026-01-17 | System | Structural polish, updated for v1.1.0 |

---

*This document represents a complete reverse-engineering of the BTC Laptop Agents codebase. A development team following this specification should be able to recreate the system with identical functionality.*
