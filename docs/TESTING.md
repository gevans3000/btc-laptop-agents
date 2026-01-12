# TESTING.md â€” Comprehensive Testing Strategy

> **Status**: ACTIVE
> **Version**: 1.0 (Aligns with v1.0.1)

This document defines the testing strategy for the `btc-laptop-agents` system. Our primary goal is **Safety**, followed by **Correctness** and **Stability**.

## 1. The Testing Pyramid

We employ a 4-tier testing strategy:

| Level | Type | Scope | Tool | Frequency |
| :--- | :--- | :--- | :--- | :--- |
| **L1** | **Unit Tests** | Individual classes/functions (e.g., `HardLimits`, `Logger`). | `pytest` | On every save/commit. |
| **L2** | **System Component Tests** | Core engine logic (Risk, Order Sizing, PnL). | `run.py --mode selftest` | Before every commit. |
| **L3** | **Integration Tests** | Full pipeline with Mock data. | `run.py --mode backtest` | Before release/deploy. |
| **L4** | **Live Verification** | Real exchange connectivity (Shadow/Live). | `watchdog` / `live-session` | Continuous in Prod. |

---

## 2. Level 1: Unit Tests

These tests isolate specific components to ensure they behave exactly as specified, especially for safety-critical modules.

### Location
`tests/` directory. Naming convention: `test_<module_name>.py`.

### Critical Coverage Areas
1.  **Safety Limits** (`src/laptop_agents/core/hard_limits.py`):
    - Verify `MAX_POSITION_SIZE` rejects large orders.
    - Verify `MAX_DAILY_LOSS` triggers.
2.  **Resilience** (`src/laptop_agents/resilience/`):
    - Verify `CircuitBreaker` states (Closed -> Open -> Half-Open).
    - Verify `RetryPolicy` exponential backoff logic.
3.  **Broker Logic** (`src/laptop_agents/execution/bitunix_broker.py`):
    - Verify Drift Detection triggers on state mismatch.
    - Verify Rounding logic works for weird tick sizes (e.g., 0.00001).

### How to Run
```powershell
# Run all unit tests
pytest tests/

# Run specific test file
pytest tests/test_hard_limits.py
```

---

## 3. Level 2: Component Self-Tests

These are fast, deterministic tests embedded in the core engine to verify the "Physics" of the trading engine.

### Scope
- **PnL Calculation**: Verifies Long/Short math, fee deduction, and slippage.
- **Order Ordering**: Ensures Entry -> Stop -> TakeProfit order is respected.
- **State Management**: Ensures `Supervisor` transitions correctly between states.

### How to Run
Included in the verification script:
```powershell
.\scripts\verify.ps1 -Mode quick
```

Or manually:
```powershell
python -m src.laptop_agents.run --mode selftest
```

---

## 4. Level 3: Integration Tests (Mock Backtest)

These tests run the entire orchestrated pipeline (Agents -> Supervisor -> Risk -> Broker) against a static set of mock candles.

### Goal
To ensure that "Plugged together, it doesn't crash."

### How to Run
```powershell
python -m src.laptop_agents.run --mode backtest --source mock --limit 100
```
**Success Criteria**:
- `runs/latest/trades.csv` is generated and non-empty.
- `runs/latest/summary.html` renders without error.
- No tracebacks in console.

---

## 5. Level 4: Live Verification

Final acceptance testing using real exchange connectivity.

### A. Shadow Mode (Safe)
Runs the logic against live data but simulates execution.
```powershell
$env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session --source bitunix --symbol BTCUSD --execution-mode paper --duration 10
```
**Verify**:
- Logs show `[PAPER]` tags (since execution-mode is paper).
- Heartbeat is updated in `logs/heartbeat.json`.

### B. Live Mode (Real)
Runs with small capital to verify full round-trip.
```powershell
$env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session --source bitunix --symbol BTCUSD --execution-mode live --duration 10
```
**Verify**:
- Orders appear on Bitunix dashboard.
- Fills are detected and logged.

## Live Trading System Tests

### Unit Tests
```powershell
$env:PYTHONPATH='src'; python scripts/test_live_system.py
```

### Integration Test (Paper Mode)
```powershell
$env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session --source bitunix --symbol BTCUSD --execution-mode paper --duration 2
```

---

## 6. Continuous Integration (CI)

We currently use a local CI script: `scripts/verify.ps1`.

### The Rule
 **"If verify.ps1 fails, do not commit."**

This script automates:
1.  **Compilation Check**: `python -m compileall`
2.  **L2 Self-Tests**: Risk engine verification.
3.  **Artifact Validation**: Checks valid JSON/CSV structure.

---

## 7. Implementation Plan (Next Steps)

To reach 100% confidence, we need to implement the following missing L1 tests:

1.  **`tests/test_hard_limits.py`**:
    - Mock a `BitunixBroker` and try to submit a $1M order. Assert `SafetyException`.
2.  **`tests/test_watchdog.py`** (or similar script check):
    - Verify that killing the subprocess triggers a restart.
3.  **`tests/test_logger.py`**:
    - Verify JSONL output is valid JSON.

## 8. writing_tests_guide.md

### Principles
- **No Mocking the Universe**: Don't mock `pandas` or `numpy`. Mock external APIs (Bitunix) only.
- **Determinism**: Use fixed seeds for any random data.
- **Speed**: Unit tests should complete in < 100ms.

### Example Template
```python
import pytest
from laptop_agents.core.hard_limits import MAX_POSITION_SIZE_USD
from laptop_agents.execution.bitunix_broker import BitunixBroker

def test_hard_limit_enforcement():
    broker = BitunixBroker(...)
    with pytest.raises(SafetyException):
        broker.place_order(qty=MAX_POSITION_SIZE_USD * 2, ...)
```


