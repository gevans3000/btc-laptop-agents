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
| Python version | `python --version` | 3.10+ | â˜ |
| Virtual environment active | `$env:VIRTUAL_ENV` | Points to `.venv` | â˜ |
| Dependencies installed | `pip list \| findstr numpy` | All requirements present | â˜ |
| Compile check | `python -m compileall src -q` | Exit code 0, no errors | â˜ |
| Working directory | `pwd` | Repo root `btc-laptop-agents` | â˜ |

### 1.2 Configuration Files

| Check | File | Pass Criteria | Status |
|-------|------|---------------|--------|
| Default config exists | `config/default.json` | File present, valid JSON | â˜ |
| Risk settings valid | `config/default.json` | `risk_pct` â‰¤ 2.0, `rr_min` â‰¥ 1.0 | â˜ |
| Kill switch present | `config/KILL_SWITCH.txt` | File exists (can be empty) | â˜ |
| Env file template | `.env.example` | Present with documented vars | â˜ |

### 1.3 API Keys & Permissions (Bitunix Mode Only)

| Check | Validation | Pass Criteria | Status |
|-------|------------|---------------|--------|
| API key format | `$env:BITUNIX_API_KEY` | Non-empty, 32+ chars | â˜ |
| API secret format | `$env:BITUNIX_API_SECRET` | Non-empty, 64+ chars | â˜ |
| Key permissions | Manual Bitunix dashboard check | Read-only OR Paper-trading only | â˜ |
| IP whitelist | Bitunix dashboard | Current IP whitelisted | â˜ |
| Test connectivity | `python -c "from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider; p=BitunixFuturesProvider(); print(p.test_connection())"` | Returns True | â˜ |

### 1.4 Hard Limits Verification

```powershell
# Verify hard limits are enforced
python -c "from laptop_agents.core import hard_limits; print(f'MAX_POSITION_SIZE_USD: {hard_limits.MAX_POSITION_SIZE_USD}'); print(f'MAX_LEVERAGE: {hard_limits.MAX_LEVERAGE}')"
```

| Limit | Expected Value | Status |
|-------|----------------|--------|
| `MAX_POSITION_SIZE_USD` | $200,000 | â˜ |
| `MAX_LEVERAGE` | 20.0x | â˜ |

---

## 2. Runtime Validation

### 2.1 Order Lifecycle Testing

#### 2.1.1 Order Creation

| Scenario | Test Command | Expected Outcome | Status |
|----------|--------------|------------------|--------|
| Market order LONG | Run with bullish signal | Fill at close price, position opened | â˜ |
| Market order SHORT | Run with bearish signal | Fill at close price, position opened | â˜ |
| Limit order within range | Inject limit order where `low â‰¤ entry â‰¤ high` | Fill at limit price | â˜ |
| Limit order out of range | Inject limit order where entry not touched | No fill, order pending | â˜ |
| Order rejected (hard limit) | Set `qty` to exceed `MAX_POSITION_SIZE_USD` | Order rejected, log warning | â˜ |
| Order rejected (leverage) | Set leverage > `MAX_LEVERAGE` | Order rejected, log warning | â˜ |

#### 2.1.2 Position Management

| Scenario | Test | Expected Outcome | Status |
|----------|------|------------------|--------|
| Stop-loss hit (LONG) | `candle.low â‰¤ sl` | Exit at SL, negative PnL | â˜ |
| Stop-loss hit (SHORT) | `candle.high â‰¥ sl` | Exit at SL, negative PnL | â˜ |
| Take-profit hit (LONG) | `candle.high â‰¥ tp` | Exit at TP, positive PnL | â˜ |
| Take-profit hit (SHORT) | `candle.low â‰¤ tp` | Exit at TP, positive PnL | â˜ |
| Both SL/TP touched | Inject candle touching both | Exit at SL (conservative) | â˜ |
| Trailing stop activation | Profit > 0.5R | Trail activates, logged | â˜ |
| Trailing stop moves favorably | New highs (LONG) | Trail ratchets up only | â˜ |
| Trailing stop triggers | Price retraces to trail | Exit at trail price | â˜ |

#### 2.1.3 PnL Calculation Accuracy

| Scenario | Formula Verification | Status |
|----------|---------------------|--------|
| Linear LONG PnL | `pnl = (exit - entry) * qty` | â˜ |
| Linear SHORT PnL | `pnl = (entry - exit) * qty` | â˜ |
| Inverse LONG PnL | `pnl = qty * (1/entry - 1/exit)` | â˜ |
| Inverse SHORT PnL | `pnl = qty * (1/exit - 1/entry)` | â˜ |
| R-multiple calculation | `r = pnl / risk` where `risk = abs(entry - sl) * qty` | â˜ |
| Fee deduction | Verify `fees_bps` applied correctly | â˜ |
| Slippage applied | Verify `slip_bps` applied to fill price | â˜ |

---

## 3. Error Handling & Edge Cases

### 3.1 Network & Connectivity

| Scenario | Simulation Method | Expected Behavior | Status |
|----------|-------------------|-------------------|--------|
| API timeout | Mock slow response (>30s) | Retry with backoff, log event | â˜ |
| Connection refused | Block network to Bitunix | Circuit breaker trips after 3 failures | â˜ |
| Rate limit (429) | Mock rate limit response | Backoff, retry after delay | â˜ |
| Malformed response | Mock invalid JSON | Log error, skip iteration, continue | â˜ |
| Partial response | Mock truncated candle data | Validate data, reject incomplete | â˜ |

### 3.2 Order Edge Cases

| Scenario | Handling | Status |
|----------|----------|--------|
| Zero quantity order | Reject with log | â˜ |
| Negative price input | Reject with log | â˜ |
| SL beyond entry (wrong side) | Reject or auto-correct | â˜ |
| TP worse than entry | Reject with log | â˜ |
| Duplicate position attempt | Reject, already in position | â˜ |
| Order on stale data (>5 min old) | Reject, log staleness warning | â˜ |

### 3.3 Circuit Breaker Validation

| Trigger | Threshold | Expected Behavior | Status |
|---------|-----------|-------------------|--------|
| Daily drawdown | >5% | Trip breaker, stop new orders | â˜ |
| Consecutive losses | >5 trades | Trip breaker, stop new orders | â˜ |
| Manual kill switch | `KILL_SWITCH.txt` present | Immediate halt, log event | â˜ |
| Circuit breaker reset | After cooldown period | Resume trading, log reset | â˜ |

### 3.4 State Recovery

| Scenario | Test Method | Expected Outcome | Status |
|----------|-------------|------------------|--------|
| Crash mid-trade | Kill process with open position | Recover position from `state.json` | â˜ |
| Corrupt state file | Inject malformed JSON | Fallback to clean state, log warning | â˜ |
| Missing state file | Delete `paper/state.json` | Initialize fresh state | â˜ |
| PID file stale | Kill process, leave PID file | `mvp_status.ps1` shows STALE | â˜ |

---

## 4. Data Integrity Checks

### 4.1 Market Data Accuracy

| Check | Validation Method | Pass Criteria | Status |
|-------|-------------------|---------------|--------|
| Candle OHLC consistency | `high â‰¥ max(open, close)` and `low â‰¤ min(open, close)` | All candles pass | â˜ |
| Timestamp ordering | `candles[i].ts < candles[i+1].ts` | Strictly ascending | â˜ |
| No duplicate timestamps | `len(set(ts)) == len(ts)` | No duplicates | â˜ |
| Volume non-negative | `volume â‰¥ 0` for all candles | True | â˜ |
| Price within bounds | No zeros, no negatives | True | â˜ |

### 4.2 Timestamp & Latency

| Check | Method | Pass Criteria | Status |
|-------|--------|---------------|--------|
| Candle freshness (Bitunix) | Compare latest candle ts to system time | â‰¤ 2 intervals stale | â˜ |
| Processing latency | Measure loop iteration time | â‰¤ 5 seconds per cycle | â˜ |
| Clock sync | Compare system time to NTP | â‰¤ 1 second drift | â˜ |

### 4.3 Replay Consistency

| Test | Method | Pass Criteria | Status |
|------|--------|---------------|--------|
| Deterministic replay | Run same candles twice | Identical `trades.csv` output | â˜ |
| Fee/slippage consistency | Compare PnL with/without fees | Difference matches expected fees | â˜ |
| Signal reproducibility | Same candles → same signals | 100% match | â˜ |

---

## 5. Logging, Monitoring & Alerting

### 5.1 Required Log Events

| Event | Location | Fields Required | Status |
|-------|----------|-----------------|--------|
| `RunStarted` | `events.jsonl` | timestamp, mode, source, params | â˜ |
| `RunFinished` | `events.jsonl` | timestamp, trades, pnl, errors | â˜ |
| `MarketDataLoaded` | `events.jsonl` | timestamp, candle_count, latest_ts | â˜ |
| `SignalGenerated` | `events.jsonl` | timestamp, signal, price, indicators | â˜ |
| `OrderPlaced` | `events.jsonl` | timestamp, side, qty, entry, sl, tp | â˜ |
| `OrderRejected` | `events.jsonl` | timestamp, reason, order_details | â˜ |
| `Fill` | `events.jsonl` | timestamp, side, price, qty | â˜ |
| `Exit` | `events.jsonl` | timestamp, reason, pnl, r_mult | â˜ |
| `CircuitBreakerTripped` | `events.jsonl` | timestamp, trigger, status | â˜ |
| `Error` | `events.jsonl` | timestamp, error_type, message, stack | â˜ |

### 5.2 Monitoring Requirements

| Metric | Collection Method | Alert Threshold | Status |
|--------|-------------------|-----------------|--------|
| Loop heartbeat | Check `events.jsonl` mtime | >5 min stale → alert | â˜ |
| Error count | Parse `Error` events | >3 in 5 min → alert | â˜ |
| Drawdown | Read circuit breaker status | >3% → warning, >5% → halt | â˜ |
| Position duration | Track `bars_open` | >100 bars → investigate | â˜ |

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
| `test_smoke.py` | Basic import/compile | `pytest tests/test_smoke.py -v` | â˜ |
| `test_safety.py` | Hard limits enforcement | `pytest tests/test_safety.py -v` | â˜ |
| `test_trailing_stop.py` | Trail stop behavior | `pytest tests/test_trailing_stop.py -v` | â˜ |
| `test_funding_gate.py` | Funding rate gates | `pytest tests/test_funding_gate.py -v` | â˜ |
| `test_paper_journal.py` | Journal logging | `pytest tests/test_paper_journal.py -v` | â˜ |
| `test_pipeline_smoke.py` | E2E pipeline | `pytest tests/test_pipeline_smoke.py -v` | â˜ |
| `test_run_reproducibility.py` | Deterministic runs | `pytest tests/test_run_reproducibility.py -v` | â˜ |

### 6.2 Required New Tests (per Phase E)

| Test File | Purpose | Priority | Status |
|-----------|---------|----------|--------|
| `test_orchestrator_legacy.py` | All legacy modes | Critical | â˜ |
| `test_orchestrator_modular.py` | Orchestrated mode | Critical | â˜ |
| `test_dual_mode.py` | Legacy vs modular parity | Critical | â˜ |
| `test_signal.py` | Signal generation edge cases | Critical | â˜ |
| `test_paper_broker.py` | Broker fill/exit logic | Critical | â˜ |
| `test_circuit_breaker.py` | Breaker trip/reset | Critical | â˜ |
| `test_loader.py` | Data loading edge cases | High | â˜ |
| `test_bitunix_provider.py` | API resilience (mocked) | High | â˜ |

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
| All tests pass | 100% green | â˜ |
| No compile errors | `python -m compileall src` clean | â˜ |
| Coverage threshold | â‰¥80% on critical paths | â˜ |
| No new warnings | Linter clean | â˜ |

---

## 7. Manual Test Scenarios

### 7.1 Scenario 1: Cold Start Verification

**Objective**: Verify system starts clean with no prior state.

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 1 | Delete `paper/` directory | Directory removed | â˜ |
| 2 | Delete `runs/` directory | Directory removed | â˜ |
| 3 | Run `.\scripts\verify.ps1 -Mode quick` | All checks pass | â˜ |
| 4 | Run `.\scripts\mvp_run_once.ps1` | Completes, creates outputs | â˜ |
| 5 | Verify `runs/latest/summary.html` exists | File present | â˜ |
| 6 | Verify `runs/latest/trades.csv` exists | File present, valid CSV | â˜ |
| 7 | Verify `runs/latest/events.jsonl` exists | File present, valid JSONL | â˜ |

### 7.2 Scenario 2: Background Process Lifecycle

**Objective**: Verify start/status/stop cycle works correctly.

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 1 | Run `.\scripts\mvp_start_live.ps1` | Process starts, PID file created | â˜ |
| 2 | Run `.\scripts\mvp_status.ps1` | Shows "ON" with PID | â˜ |
| 3 | Wait 2 minutes | Events appear in `paper/events.jsonl` | â˜ |
| 4 | Run `.\scripts\mvp_stop_live.ps1` | Process stops, PID file removed | â˜ |
| 5 | Run `.\scripts\mvp_status.ps1` | Shows "OFF" | â˜ |

### 7.3 Scenario 3: Trade Execution Verification

**Objective**: Verify a complete trade lifecycle.

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 1 | Inject bullish mock data | Signal generated: LONG | â˜ |
| 2 | Verify fill event | Position opened at expected price | â˜ |
| 3 | Verify SL/TP set | Both present in state | â˜ |
| 4 | Inject TP-hitting candle | Position closed at TP | â˜ |
| 5 | Verify PnL calculation | Matches manual calculation | â˜ |
| 6 | Verify trade logged | Appears in `trades.csv` | â˜ |

### 7.4 Scenario 4: Circuit Breaker Trip

**Objective**: Verify circuit breaker stops trading on drawdown.

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 1 | Set starting equity = $10,000 | State initialized | â˜ |
| 2 | Simulate 5% loss sequence | Equity drops to $9,500 | â˜ |
| 3 | Verify `CircuitBreakerTripped` event | Event logged | â˜ |
| 4 | Attempt new signal | Order rejected, breaker tripped | â˜ |
| 5 | Verify existing position management | Exits still processed | â˜ |

### 7.5 Scenario 5: Crash Recovery

**Objective**: Verify state persists across crashes.

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 1 | Start session, enter position | Position in state.json | â˜ |
| 2 | Kill process (Ctrl+C or Task Manager) | Process terminated | â˜ |
| 3 | Verify `paper/state.json` intact | Position data present | â˜ |
| 4 | Restart session | Position recovered, continues | â˜ |
| 5 | Verify no duplicate entries | No ghost positions | â˜ |

### 7.6 Scenario 6: Bitunix Integration (If Enabled)

**Objective**: Verify real market data integration.

| Step | Action | Expected Result | Pass/Fail |
|------|--------|-----------------|-----------|
| 1 | Set `--source bitunix` | Uses Bitunix provider | â˜ |
| 2 | Verify API connection | No auth errors | â˜ |
| 3 | Verify candle data received | Fresh timestamps | â˜ |
| 4 | Verify paper order (not real) | No actual exchange orders | â˜ |
| 5 | Verify rate limiting respected | No 429 errors | â˜ |

---

## 8. Go/No-Go Readiness Checklist

### 8.1 Critical Blockers (All Must Pass)

| # | Criterion | Evidence Required | Status |
|---|-----------|-------------------|--------|
| 1 | All automated tests pass | `pytest` output: 100% pass | â˜ |
| 2 | No compile errors | `python -m compileall src` clean | â˜ |
| 3 | Hard limits enforced | `test_safety.py` passes | â˜ |
| 4 | Circuit breaker functional | Manual + automated tests pass | â˜ |
| 5 | No real orders possible | Code audit confirms paper-only | â˜ |
| 6 | State persistence verified | Crash recovery test passes | â˜ |
| 7 | PnL calculations verified | Manual spot-check matches | â˜ |
| 8 | Kill switch operational | Manual test confirms halt | â˜ |

### 8.2 High Priority (Should Pass)

| # | Criterion | Evidence Required | Status |
|---|-----------|-------------------|--------|
| 9 | Test coverage â‰¥ 80% | Coverage report | â˜ |
| 10 | All manual scenarios pass | Sign-off on each | â˜ |
| 11 | No ERROR-level log spam | Clean 24h run | â˜ |
| 12 | Documentation current | README matches reality | â˜ |
| 13 | Retry logic verified | Mocked failure tests pass | â˜ |
| 14 | Trailing stop works correctly | `test_trailing_stop.py` passes | â˜ |

### 8.3 Nice to Have (Recommended)

| # | Criterion | Evidence Required | Status |
|---|-----------|-------------------|--------|
| 15 | Monitoring dashboard functional | `scripts/monitor.py` works | â˜ |
| 16 | 48h unattended run stable | No crashes, expected behavior | â˜ |
| 17 | Bitunix integration tested | If using real data | â˜ |
| 18 | Config validation on startup | Bad config → clear error | â˜ |

### 8.4 Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | â˜ |
| QA Reviewer | | | â˜ |
| System Owner | | | â˜ |

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

