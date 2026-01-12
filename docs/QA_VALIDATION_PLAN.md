# QA Validation Plan: Paper Trading Readiness

> **Status**: ACTIVE  
> **Goal**: Zero critical errors, verified paper trading correctness before live deployment  
> **Last Updated**: 2026-01-12

---

## Table of Contents

1. [Pre-Run Configuration Checks](#1-pre-run-configuration-checks)
2. [Runtime Validation](#2-runtime-validation)
3. [Error Handling & Edge Cases](#3-error-handling--edge-cases)
4. [Data Integrity Checks](#4-data-integrity-checks)
5. [Logging, Monitoring & Alerting](#5-logging-monitoring--alerting)
6. [Automated Tests](#6-automated-tests)
7. [Manual Test Scenarios](#7-manual-test-scenarios)
8. [Go/No-Go Readiness Checklist](#8-gono-go-readiness-checklist)

---

## 1. Pre-Run Configuration Checks

### 1.1 Environment Verification

| Check | Command/Action | Pass Criteria | Status |
|-------|----------------|---------------|--------|
| Python version | `python --version` | 3.10+ | ☐ |
| Virtual environment active | `$env:VIRTUAL_ENV` | Points to `.venv` | ☐ |
| Dependencies installed | `pip list \| findstr numpy` | All requirements present | ☐ |
| Compile check | `python -m compileall src -q` | Exit code 0, no errors | ☐ |
| Working directory | `pwd` | Repo root `btc-laptop-agents` | ☐ |

### 1.2 Configuration Files

| Check | File | Pass Criteria | Status |
|-------|------|---------------|--------|
| Default config exists | `config/default.json` | File present, valid JSON | ☐ |
| Risk settings valid | `config/default.json` | `risk_pct` ≤ 2.0, `rr_min` ≥ 1.0 | ☐ |
| Kill switch present | `config/KILL_SWITCH.txt` | File exists (can be empty) | ☐ |
| Env file template | `.env.example` | Present with documented vars | ☐ |

### 1.3 API Keys & Permissions (Bitunix Mode Only)

| Check | Validation | Pass Criteria | Status |
|-------|------------|---------------|--------|
| API key format | `$env:BITUNIX_API_KEY` | Non-empty, 32+ chars | ☐ |
| API secret format | `$env:BITUNIX_API_SECRET` | Non-empty, 64+ chars | ☐ |
| Key permissions | Manual Bitunix dashboard check | Read-only OR Paper-trading only | ☐ |
| IP whitelist | Bitunix dashboard | Current IP whitelisted | ☐ |
| Test connectivity | `python -c "from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider; p=BitunixFuturesProvider(); print(p.test_connection())"` | Returns True | ☐ |

### 1.4 Hard Limits Verification

```powershell
# Verify hard limits are enforced
python -c "from laptop_agents.core import hard_limits; print(f'MAX_POSITION_SIZE_USD: {hard_limits.MAX_POSITION_SIZE_USD}'); print(f'MAX_LEVERAGE: {hard_limits.MAX_LEVERAGE}')"
```

| Limit | Expected Value | Status |
|-------|----------------|--------|
| `MAX_POSITION_SIZE_USD` | $200,000 | ☐ |
| `MAX_LEVERAGE` | 20.0x | ☐ |

---

## 2. Runtime Validation

### 2.1 Order Lifecycle Testing

#### 2.1.1 Order Creation

| Scenario | Test Command | Expected Outcome | Status |
|----------|--------------|------------------|--------|
| Market order LONG | Run with bullish signal | Fill at close price, position opened | ☐ |
| Market order SHORT | Run with bearish signal | Fill at close price, position opened | ☐ |
| Limit order within range | Inject limit order where `low ≤ entry ≤ high` | Fill at limit price | ☐ |
| Limit order out of range | Inject limit order where entry not touched | No fill, order pending | ☐ |
| Order rejected (hard limit) | Set `qty` to exceed `MAX_POSITION_SIZE_USD` | Order rejected, log warning | ☐ |
| Order rejected (leverage) | Set leverage > `MAX_LEVERAGE` | Order rejected, log warning | ☐ |

#### 2.1.2 Position Management

| Scenario | Test | Expected Outcome | Status |
|----------|------|------------------|--------|
| Stop-loss hit (LONG) | `candle.low ≤ sl` | Exit at SL, negative PnL | ☐ |
| Stop-loss hit (SHORT) | `candle.high ≥ sl` | Exit at SL, negative PnL | ☐ |
| Take-profit hit (LONG) | `candle.high ≥ tp` | Exit at TP, positive PnL | ☐ |
| Take-profit hit (SHORT) | `candle.low ≤ tp` | Exit at TP, positive PnL | ☐ |
| Both SL/TP touched | Inject candle touching both | Exit at SL (conservative) | ☐ |
| Trailing stop activation | Profit > 0.5R | Trail activates, logged | ☐ |
| Trailing stop moves favorably | New highs (LONG) | Trail ratchets up only | ☐ |
| Trailing stop triggers | Price retraces to trail | Exit at trail price | ☐ |

#### 2.1.3 PnL Calculation Accuracy

| Scenario | Formula Verification | Status |
|----------|---------------------|--------|
| Linear LONG PnL | `pnl = (exit - entry) * qty` | ☐ |
| Linear SHORT PnL | `pnl = (entry - exit) * qty` | ☐ |
| Inverse LONG PnL | `pnl = qty * (1/entry - 1/exit)` | ☐ |
| Inverse SHORT PnL | `pnl = qty * (1/exit - 1/entry)` | ☐ |
| R-multiple calculation | `r = pnl / risk` where `risk = abs(entry - sl) * qty` | ☐ |
| Fee deduction | Verify `fees_bps` applied correctly | ☐ |
| Slippage applied | Verify `slip_bps` applied to fill price | ☐ |

---

## 3. Error Handling & Edge Cases

### 3.1 Network & Connectivity

| Scenario | Simulation Method | Expected Behavior | Status |
|----------|-------------------|-------------------|--------|
| API timeout | Mock slow response (>30s) | Retry with backoff, log event | ☐ |
| Connection refused | Block network to Bitunix | Circuit breaker trips after 3 failures | ☐ |
| Rate limit (429) | Mock rate limit response | Backoff, retry after delay | ☐ |
| Malformed response | Mock invalid JSON | Log error, skip iteration, continue | ☐ |
| Partial response | Mock truncated candle data | Validate data, reject incomplete | ☐ |

### 3.2 Order Edge Cases

| Scenario | Handling | Status |
|----------|----------|--------|
| Zero quantity order | Reject with log | ☐ |
| Negative price input | Reject with log | ☐ |
| SL beyond entry (wrong side) | Reject or auto-correct | ☐ |
| TP worse than entry | Reject with log | ☐ |
| Duplicate position attempt | Reject, already in position | ☐ |
| Order on stale data (>5 min old) | Reject, log staleness warning | ☐ |

### 3.3 Circuit Breaker Validation

| Trigger | Threshold | Expected Behavior | Status |
|---------|-----------|-------------------|--------|
| Daily drawdown | >5% | Trip breaker, stop new orders | ☐ |
| Consecutive losses | >5 trades | Trip breaker, stop new orders | ☐ |
| Manual kill switch | `KILL_SWITCH.txt` present | Immediate halt, log event | ☐ |
| Circuit breaker reset | After cooldown period | Resume trading, log reset | ☐ |

### 3.4 State Recovery

| Scenario | Test Method | Expected Outcome | Status |
|----------|-------------|------------------|--------|
| Crash mid-trade | Kill process with open position | Recover position from `state.json` | ☐ |
| Corrupt state file | Inject malformed JSON | Fallback to clean state, log warning | ☐ |
| Missing state file | Delete `paper/state.json` | Initialize fresh state | ☐ |
| PID file stale | Kill process, leave PID file | `mvp_status.ps1` shows STALE | ☐ |

---

## 4. Data Integrity Checks

### 4.1 Market Data Accuracy

| Check | Validation Method | Pass Criteria | Status |
|-------|-------------------|---------------|--------|
| Candle OHLC consistency | `high ≥ max(open, close)` and `low ≤ min(open, close)` | All candles pass | ☐ |
| Timestamp ordering | `candles[i].ts < candles[i+1].ts` | Strictly ascending | ☐ |
| No duplicate timestamps | `len(set(ts)) == len(ts)` | No duplicates | ☐ |
| Volume non-negative | `volume ≥ 0` for all candles | True | ☐ |
| Price within bounds | No zeros, no negatives | True | ☐ |

### 4.2 Timestamp & Latency

| Check | Method | Pass Criteria | Status |
|-------|--------|---------------|--------|
| Candle freshness (Bitunix) | Compare latest candle ts to system time | ≤ 2 intervals stale | ☐ |
| Processing latency | Measure loop iteration time | ≤ 5 seconds per cycle | ☐ |
| Clock sync | Compare system time to NTP | ≤ 1 second drift | ☐ |

### 4.3 Replay Consistency

| Test | Method | Pass Criteria | Status |
|------|--------|---------------|--------|
| Deterministic replay | Run same candles twice | Identical `trades.csv` output | ☐ |
| Fee/slippage consistency | Compare PnL with/without fees | Difference matches expected fees | ☐ |
| Signal reproducibility | Same candles → same signals | 100% match | ☐ |

---

## 5. Logging, Monitoring & Alerting

### 5.1 Required Log Events

| Event | Location | Fields Required | Status |
|-------|----------|-----------------|--------|
| `RunStarted` | `events.jsonl` | timestamp, mode, source, params | ☐ |
| `RunFinished` | `events.jsonl` | timestamp, trades, pnl, errors | ☐ |
| `MarketDataLoaded` | `events.jsonl` | timestamp, candle_count, latest_ts | ☐ |
| `SignalGenerated` | `events.jsonl` | timestamp, signal, price, indicators | ☐ |
| `OrderPlaced` | `events.jsonl` | timestamp, side, qty, entry, sl, tp | ☐ |
| `OrderRejected` | `events.jsonl` | timestamp, reason, order_details | ☐ |
| `Fill` | `events.jsonl` | timestamp, side, price, qty | ☐ |
| `Exit` | `events.jsonl` | timestamp, reason, pnl, r_mult | ☐ |
| `CircuitBreakerTripped` | `events.jsonl` | timestamp, trigger, status | ☐ |
| `Error` | `events.jsonl` | timestamp, error_type, message, stack | ☐ |

### 5.2 Monitoring Requirements

| Metric | Collection Method | Alert Threshold | Status |
|--------|-------------------|-----------------|--------|
| Loop heartbeat | Check `events.jsonl` mtime | >5 min stale → alert | ☐ |
| Error count | Parse `Error` events | >3 in 5 min → alert | ☐ |
| Drawdown | Read circuit breaker status | >3% → warning, >5% → halt | ☐ |
| Position duration | Track `bars_open` | >100 bars → investigate | ☐ |

### 5.3 Log Retention

| Log Type | Retention | Location |
|----------|-----------|----------|
| Current run events | Until next run | `runs/latest/events.jsonl` |
| Archived runs | 30 days | `runs/YYYYMMDD_HHMMSS/` |
| Paper trading state | Persistent | `paper/state.json` |
| Error logs | 7 days | `paper/live.err.txt` |

---

## 6. Automated Tests

### 6.1 Existing Test Coverage

| Test File | Coverage Area | Run Command | Status |
|-----------|---------------|-------------|--------|
| `test_smoke.py` | Basic import/compile | `pytest tests/test_smoke.py -v` | ☐ |
| `test_safety.py` | Hard limits enforcement | `pytest tests/test_safety.py -v` | ☐ |
| `test_trailing_stop.py` | Trail stop behavior | `pytest tests/test_trailing_stop.py -v` | ☐ |
| `test_funding_gate.py` | Funding rate gates | `pytest tests/test_funding_gate.py -v` | ☐ |
| `test_paper_journal.py` | Journal logging | `pytest tests/test_paper_journal.py -v` | ☐ |
| `test_pipeline_smoke.py` | E2E pipeline | `pytest tests/test_pipeline_smoke.py -v` | ☐ |
| `test_run_reproducibility.py` | Deterministic runs | `pytest tests/test_run_reproducibility.py -v` | ☐ |

### 6.2 Required New Tests (per Phase E)

| Test File | Purpose | Priority | Status |
|-----------|---------|----------|--------|
| `test_orchestrator_legacy.py` | All legacy modes | Critical | ☐ |
| `test_orchestrator_modular.py` | Orchestrated mode | Critical | ☐ |
| `test_dual_mode.py` | Legacy vs modular parity | Critical | ☐ |
| `test_signal.py` | Signal generation edge cases | Critical | ☐ |
| `test_paper_broker.py` | Broker fill/exit logic | Critical | ☐ |
| `test_circuit_breaker.py` | Breaker trip/reset | Critical | ☐ |
| `test_loader.py` | Data loading edge cases | High | ☐ |
| `test_bitunix_provider.py` | API resilience (mocked) | High | ☐ |

### 6.3 Test Execution Commands

```powershell
# Full test suite
pytest tests/ -v --tb=short

# With coverage
pytest tests/ --cov=src/laptop_agents --cov-report=html

# Quick smoke test
pytest tests/test_smoke.py tests/test_safety.py -v

# Integration tests only
pytest tests/test_pipeline_smoke.py tests/test_run_reproducibility.py -v
```

### 6.4 CI/CD Pass Criteria

| Gate | Requirement | Status |
|------|-------------|--------|
| All tests pass | 100% green | ☐ |
| No compile errors | `python -m compileall src` clean | ☐ |
| Coverage threshold | ≥80% on critical paths | ☐ |
| No new warnings | Linter clean | ☐ |

---

## 7. Manual Test Scenarios

### 7.1 Scenario 1: Cold Start Verification

**Objective**: Verify system starts clean with no prior state.

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 1 | Delete `paper/` directory | Directory removed | ☐ |
| 2 | Delete `runs/` directory | Directory removed | ☐ |
| 3 | Run `.\scripts\verify.ps1 -Mode quick` | All checks pass | ☐ |
| 4 | Run `.\scripts\mvp_run_once.ps1` | Completes, creates outputs | ☐ |
| 5 | Verify `runs/latest/summary.html` exists | File present | ☐ |
| 6 | Verify `runs/latest/trades.csv` exists | File present, valid CSV | ☐ |
| 7 | Verify `runs/latest/events.jsonl` exists | File present, valid JSONL | ☐ |

### 7.2 Scenario 2: Background Process Lifecycle

**Objective**: Verify start/status/stop cycle works correctly.

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 1 | Run `.\scripts\mvp_start_live.ps1` | Process starts, PID file created | ☐ |
| 2 | Run `.\scripts\mvp_status.ps1` | Shows "ON" with PID | ☐ |
| 3 | Wait 2 minutes | Events appear in `paper/events.jsonl` | ☐ |
| 4 | Run `.\scripts\mvp_stop_live.ps1` | Process stops, PID file removed | ☐ |
| 5 | Run `.\scripts\mvp_status.ps1` | Shows "OFF" | ☐ |

### 7.3 Scenario 3: Trade Execution Verification

**Objective**: Verify a complete trade lifecycle.

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 1 | Inject bullish mock data | Signal generated: LONG | ☐ |
| 2 | Verify fill event | Position opened at expected price | ☐ |
| 3 | Verify SL/TP set | Both present in state | ☐ |
| 4 | Inject TP-hitting candle | Position closed at TP | ☐ |
| 5 | Verify PnL calculation | Matches manual calculation | ☐ |
| 6 | Verify trade logged | Appears in `trades.csv` | ☐ |

### 7.4 Scenario 4: Circuit Breaker Trip

**Objective**: Verify circuit breaker stops trading on drawdown.

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 1 | Set starting equity = $10,000 | State initialized | ☐ |
| 2 | Simulate 5% loss sequence | Equity drops to $9,500 | ☐ |
| 3 | Verify `CircuitBreakerTripped` event | Event logged | ☐ |
| 4 | Attempt new signal | Order rejected, breaker tripped | ☐ |
| 5 | Verify existing position management | Exits still processed | ☐ |

### 7.5 Scenario 5: Crash Recovery

**Objective**: Verify state persists across crashes.

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 1 | Start session, enter position | Position in state.json | ☐ |
| 2 | Kill process (Ctrl+C or Task Manager) | Process terminated | ☐ |
| 3 | Verify `paper/state.json` intact | Position data present | ☐ |
| 4 | Restart session | Position recovered, continues | ☐ |
| 5 | Verify no duplicate entries | No ghost positions | ☐ |

### 7.6 Scenario 6: Bitunix Integration (If Enabled)

**Objective**: Verify real market data integration.

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 1 | Set `--source bitunix` | Uses Bitunix provider | ☐ |
| 2 | Verify API connection | No auth errors | ☐ |
| 3 | Verify candle data received | Fresh timestamps | ☐ |
| 4 | Verify paper order (not real) | No actual exchange orders | ☐ |
| 5 | Verify rate limiting respected | No 429 errors | ☐ |

---

## 8. Go/No-Go Readiness Checklist

### 8.1 Critical Blockers (All Must Pass)

| # | Criterion | Evidence Required | Status |
|---|-----------|-------------------|--------|
| 1 | All automated tests pass | `pytest` output: 100% pass | ☐ |
| 2 | No compile errors | `python -m compileall src` clean | ☐ |
| 3 | Hard limits enforced | `test_safety.py` passes | ☐ |
| 4 | Circuit breaker functional | Manual + automated tests pass | ☐ |
| 5 | No real orders possible | Code audit confirms paper-only | ☐ |
| 6 | State persistence verified | Crash recovery test passes | ☐ |
| 7 | PnL calculations verified | Manual spot-check matches | ☐ |
| 8 | Kill switch operational | Manual test confirms halt | ☐ |

### 8.2 High Priority (Should Pass)

| # | Criterion | Evidence Required | Status |
|---|-----------|-------------------|--------|
| 9 | Test coverage ≥ 80% | Coverage report | ☐ |
| 10 | All manual scenarios pass | Sign-off on each | ☐ |
| 11 | No ERROR-level log spam | Clean 24h run | ☐ |
| 12 | Documentation current | README matches reality | ☐ |
| 13 | Retry logic verified | Mocked failure tests pass | ☐ |
| 14 | Trailing stop works correctly | `test_trailing_stop.py` passes | ☐ |

### 8.3 Nice to Have (Recommended)

| # | Criterion | Evidence Required | Status |
|---|-----------|-------------------|--------|
| 15 | Monitoring dashboard functional | `scripts/monitor.py` works | ☐ |
| 16 | 48h unattended run stable | No crashes, expected behavior | ☐ |
| 17 | Bitunix integration tested | If using real data | ☐ |
| 18 | Config validation on startup | Bad config → clear error | ☐ |

### 8.4 Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | ☐ |
| QA Reviewer | | | ☐ |
| System Owner | | | ☐ |

---

## Appendix A: Quick Validation Commands

```powershell
# 1. Full verification
.\scripts\verify.ps1 -Mode full

# 2. Run all tests
pytest tests/ -v --tb=short

# 3. Single run with mock data
python -m src.laptop_agents.run --mode single --source mock

# 4. Orchestrated mode test
python -m src.laptop_agents.run --mode orchestrated --source mock --dry-run

# 5. Check hard limits are wired
python -c "from laptop_agents.core import hard_limits; print(vars(hard_limits))"

# 6. Validate config file
python -c "import json; json.load(open('config/default.json')); print('Config valid')"

# 7. Test circuit breaker
python -c "from laptop_agents.resilience.trading_circuit_breaker import TradingCircuitBreaker; cb=TradingCircuitBreaker(); cb.set_starting_equity(10000); cb.update_equity(9400, -600); print(f'Tripped: {cb.is_tripped()}')"
```

---

## Appendix B: Known Issues & Mitigations

| Issue | Severity | Mitigation | Tracking |
|-------|----------|------------|----------|
| Candle type duplication | Medium | Phase E2.1 unification | E2.1 |
| Live mode semantics unclear | High | Phase E4.1 explicit modes | E4.1 |
| Missing retry wrappers | Medium | Phase E4.2 implementation | E4.2 |

---

## Appendix C: Test Data Requirements

| Data Set | Purpose | Location |
|----------|---------|----------|
| Mock bullish trend | Test LONG signals | Built into mock loader |
| Mock bearish trend | Test SHORT signals | Built into mock loader |
| Mock sideways chop | Test signal filtering | Needs creation |
| Mock gap candles | Test edge handling | Needs creation |
| Historical Bitunix data | Replay consistency | `data/historical/` |

---

**Document Owner**: QA Lead  
**Review Cycle**: Before each release  
**Next Review**: Phase E completion
