# Phase E Implementation Plan: Hardening & Live-Readiness

> **Status**: IN PROGRESS  
> **Goal**: Prepare the system for safe live trading with comprehensive testing, resilience, and observability.

---

## Executive Summary

Phase E focuses on **hardening** the system for live trading:
1. Fill critical test gaps
2. Clean up core models (Candle, config)
3. Make live Bitunix trading explicit and safe
4. Add minimal observability
5. Update documentation

**Estimated Effort**: 5-8 days total

---

## Workstream Overview

| ID | Workstream | Priority | Effort | Dependencies |
| :--- | :--- | :--- | :--- | :--- |
| E1 | Testing & Correctness | ðŸ”´ Critical | L | None |
| E2 | Core Model & Config Cleanup | ðŸ”´ Critical | M | None |
| E3 | Strategy Surface & Improvements | ðŸŸ¡ High | M | E2 |
| E4 | Resilience & Live Trading | ðŸ”´ Critical | L | E1, E2 |
| E5 | Data Sources & Streaming | ðŸŸ¢ Medium | M | E2 |
| E6 | Observability & Docs | ðŸŸ¡ High | M | E1-E4 |

---

## E1: Testing & Correctness (Priority: Critical)

**Goal**: Prevent regressions and ensure orchestrated/legacy paths behave correctly.

### Tasks

#### E1.1 Orchestrator Integration Tests
- [ ] Create `tests/test_orchestrator_legacy.py`
  - Test modes: `single`, `backtest` (bar + position), `live`, `validate`, `selftest`
  - Assert artifacts created: `trades.csv`, `state.json`, `summary.html`
  - Assert events: `RunStarted`, `RunFinished`
- [ ] Create `tests/test_orchestrator_modular.py`
  - Test `run_orchestrated_mode` with `source="mock"`
  - Assert success and artifact validation

#### E1.2 Dual-Mode Consistency Tests
- [ ] Create `tests/test_dual_mode.py`
  - Same candle fixture for legacy and orchestrated
  - Both produce valid outputs (validated CSV/events/HTML)
  - No uncaught exceptions
  - Fee/slippage parameters respected

#### E1.3 Unit Tests for Core Components
- [ ] `tests/test_signal.py`
  - Insufficient candles edge case
  - Low ATR volatility â†’ `None`
  - Clear bullish/bearish crossovers
- [ ] `tests/test_paper_broker.py`
  - Trailing stop behavior (long/short)
  - Stop moves only in favorable direction
- [ ] `tests/test_supervisor_step.py`
  - Agents A1-A5 run without error
  - `pending_trigger_max_bars` behavior
  - `RiskGateAgent` can cancel orders
- [ ] `tests/test_circuit_breaker.py`
  - Drawdown threshold trips breaker
  - Consecutive losses trips breaker
  - Stops new trades when tripped

#### E1.4 Data Loader Tests
- [ ] `tests/test_loader.py`
  - `load_mock_candles` returns ordered candles
  - `normalize_candle_order` handles reverse input
- [ ] `tests/test_bitunix_provider.py` (mocked)
  - Normal data retrieval
  - Transient network errors
  - Rate-limit responses

**Deliverables**: 6-8 new test files, >80% coverage on critical paths

---

## E2: Core Model & Config Cleanup (Priority: Critical)

**Goal**: Remove duplicated types, centralize configuration.

### Tasks

#### E2.1 Unify Candle Definition
- [ ] Create `src/laptop_agents/trading/candles.py`
  ```python
  from dataclasses import dataclass
  from typing import Union
  
  @dataclass(frozen=True)
  class Candle:
      ts: str  # ISO8601 or int timestamp
      open: float
      high: float
      low: float
      close: float
      volume: float = 0.0
  ```
- [ ] Update all imports:
  - `helpers.py` â†’ import from `candles.py`
  - `indicators.py` â†’ import from `candles.py`
  - `signal.py`, `exec_engine.py`, `orchestrator.py`, `supervisor.py`, `loader.py`
- [ ] Delete duplicate `Candle` definitions
- [ ] Add `tests/test_candle_model.py`

#### E2.2 Config Loader from default.json
- [ ] Create `src/laptop_agents/config/loader.py`
  ```python
  def load_config(overrides: dict = None) -> dict:
      # Load default.json
      # Apply CLI overrides
      # Return merged config
  ```
- [ ] Update `get_agent_config` to use `load_config`
- [ ] Add `--print-config` CLI option for debugging

#### E2.3 Align Risk/Settings Semantics
- [ ] Standardize `risk_pct`: always % (1.0 = 1%)
- [ ] Align `default.json` with `get_agent_config` defaults
- [ ] Document units in config comments

**Deliverables**: Single Candle type, config loader, aligned settings

---

## E3: Strategy Surface & Improvements (Priority: High)

**Goal**: Make strategy experimentation easy without touching core.

### Tasks

#### E3.1 Strategy Protocol
- [ ] Define `Strategy` protocol in `src/laptop_agents/trading/strategy.py`
  ```python
  from typing import Protocol, Optional, List
  from .candles import Candle
  
  class Strategy(Protocol):
      def generate_signal(self, candles: List[Candle]) -> Optional[str]: ...
  ```
- [ ] Wrap existing SMA+ATR as `SmaAtrStrategy`
- [ ] Allow strategy injection in backtest/single modes

#### E3.2 Validation Grid Integration
- [ ] Ensure validation mode uses strategy abstraction
- [ ] Document parameter tuning in `docs/STRATEGIES.md`
- [ ] Add example grid search command in RUNBOOK

#### E3.3 Modular Agents Setup Testing
- [ ] Test `pullback_ribbon` with synthetic data
- [ ] Test `sweep_invalidation` with swing sweeps
- [ ] Confirm `rr_min` honored by `_resolve_order`

**Deliverables**: Strategy protocol, one wrapper, tested setups

---

## E4: Resilience & Live Trading (Priority: Critical)

**Goal**: Make Bitunix live trading unambiguous, safe, and robust.

### Tasks

#### E4.1 Clarify Live Modes
- [x] Define explicit mode semantics:
  - `backtest`: Historical simulation
  - `live-paper`: Paper trading on fresh candles (no real orders)
  - `live-exchange`: Actual Bitunix orders
- [x] Update CLI:
  - `--mode live` -> live-paper
  - `--mode live-exchange` -> requires explicit flag + env vars
- [x] Add safety checks: refuse live-exchange without API keys

#### E4.2 Wire Retry Logic
- [ ] Identify all external boundaries:
  - `BitunixFuturesProvider` REST calls
  - Future websocket connections
- [ ] Wrap with retry helper (exponential backoff + jitter)
- [ ] Add tests for transient failures

#### E4.3 Integrate Circuit Breaker
- [ ] Ensure circuit breaker works in:
  - `run_live_paper_trading`
  - `run_orchestrated_mode` (already done)
  - Future streaming mode
- [ ] Emit events: `CircuitBreakerTripped`, `CircuitBreakerReset`
- [ ] Stop new orders when tripped, continue processing exits

#### E4.4 Harden BitunixBroker
- [x] Standardize broker interface with PaperBroker
- [x] Handle min notional, lot size, leverage constraints
- [x] Use retry wrappers for network errors
- [x] Add "dry-run-live" mode (real data, paper orders)

**Deliverables**: Clear mode semantics, retry wrappers, hardened broker

---

## E5: Data Sources & Streaming (Priority: Medium)

**Goal**: Add minimal streaming machinery for future expansion.

### Tasks

#### E5.1 Market Data Feed Interface
- [ ] Define `MarketDataFeed` protocol
  ```python
  class MarketDataFeed(Protocol):
      def get_historical(self, symbol: str, interval: str, limit: int) -> List[Candle]: ...
      def stream(self, symbol: str, interval: str) -> Iterator[Candle]: ...
  ```
- [ ] Implement `MockFeed` (uses `load_mock_candles`)
- [ ] Implement `BitunixFeed` (REST for historical, polling for stream initially)

#### E5.2 Streaming Session Loop
- [ ] Create `run_streaming_session(feed, supervisor, state)`
- [ ] Integrate with circuit breaker
- [ ] Test with `MockFeed.stream`

#### E5.3 Additional Provider Placeholder
- [ ] Add stub for `BinanceFeed` or `CCXTFeed`
- [ ] Implement only `get_historical` (not wired in yet)

**Deliverables**: Feed interface, mock streaming, placeholder for expansion

---

## E6: Observability & Documentation (Priority: High)

**Goal**: Make it easy to understand what's happening in real time.

### Tasks

#### E6.1 Real-Time Monitoring
- [ ] Create `scripts/monitor.py`
  - Tail `runs/latest/events.jsonl`
  - Print compact view: time, event, key fields
- [ ] Optional: Simple Streamlit dashboard
  - Equity curve
  - Open positions
  - Recent trades
  - Circuit breaker status

#### E6.2 Structured Logging Improvements
- [x] Standardize event schema:
  - `RunStarted`, `MarketDataLoaded`, `OrderPlaced`, `OrderRejected`
  - `Fill`, `CircuitBreakerTripped`, `CheckpointSaved`
- [ ] Document event schema in `docs/EVENTS.md`

#### E6.3 Documentation Updates
- [ ] **README.md**: Architecture overview, mode matrix, quickstart
- [ ] **docs/CONFIG.md**: Explain `default.json` fields, CLI overrides
- [ ] **docs/RUNBOOK.md**: Start, monitor, stop procedures
- [ ] **docs/STRATEGIES.md**: Strategy abstraction, tuning guide

**Deliverables**: Monitor CLI, event schema docs, updated README/RUNBOOK

---

## Implementation Order

### Week 1: Foundation
1. **E2.1**: Unify Candle (blocks everything)
2. **E2.2**: Config loader
3. **E1.3**: Unit tests for signal, broker, circuit breaker

### Week 2: Testing & Safety
4. **E1.1-E1.2**: Orchestrator integration tests
5. **E4.1**: Clarify live modes
6. **E4.3**: Circuit breaker integration

### Week 3: Live Readiness
7. **E4.2**: Retry logic
8. **E4.4**: BitunixBroker hardening
9. **E3.1**: Strategy protocol

### Week 4: Polish
10. **E5.1-E5.2**: Streaming foundation
11. **E6.1-E6.3**: Monitoring & docs

---

## Success Criteria

| Criteria | Measurement |
| :--- | :--- |
| Test Coverage | >80% on core paths |
| Single Candle Type | No duplicate definitions |
| Config From File | `default.json` loaded at startup |
| Live Mode Clarity | Explicit `--mode live-exchange` flag |
| Retry Coverage | All external calls wrapped |
| Circuit Breaker | Works in all trading modes |
| Monitoring | `scripts/monitor.py` functional |
| Documentation | README/RUNBOOK up to date |

---

## Risks & Mitigations

| Risk | Mitigation |
| :--- | :--- |
| Live trading accidents | Require explicit `--mode live-exchange` + env var check |
| Config drift | Add `--print-config` to dump effective config |
| Retry over-aggressiveness | Cap retry time, log "backoff escalation" events |
| Circuit breaker misconfiguration | Include settings in events, add boundary tests |

---

## Next Steps

1. Review and approve this plan
2. Create GitHub issues for each E*.* task
3. Start with E2.1 (Unify Candle) as it unblocks everything
4. Run `verify.ps1` after each task completion

