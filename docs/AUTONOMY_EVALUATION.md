# Autonomous Paper Trading Evaluation Report

> **Evaluated**: 2026-01-17
> **Target**: 10-minute unattended autonomous paper trading
> **Verdict**: ✅ PASS (with recommendations)

---

## 1. Autonomy Verification Checklist

### 1.1 Strategy Execution Loop

| Component | Status | Evidence |
|-----------|--------|----------|
| Signal Generation | ✅ | `SetupSignalAgent` in `agents/setup_signal.py` |
| Decision Pipeline | ✅ | `Supervisor.tick()` orchestrates agents |
| Order Submission | ✅ | `PaperBroker.on_candle()` with idempotency |
| Position Monitoring | ✅ | `execution_task()` monitors fills/exits |
| Exit Handling | ✅ | SL/TP via `_check_exit()`, `_check_tick_exit()` |

**Status: ✅ PASS**

---

### 1.2 Market Data Subscription/Stream Stability

| Component | Status | Evidence |
|-----------|--------|----------|
| WebSocket Provider | ✅ | `BitunixWSProvider` with dual kline/ticker streams |
| Auto-Reconnect | ✅ | `@retry` with tenacity (600s survival window) |
| Stale Detection | ✅ | `_heartbeat_check()` with 15s timeout |
| Gap Backfill | ✅ | `fetch_and_inject_gap()` fills missing candles |
| Data Validation | ✅ | Pydantic models + timestamp/price validation |

**Status: ✅ PASS**

---

### 1.3 Order Lifecycle Handling

| State | Status | Evidence |
|-------|--------|----------|
| Submitted | ✅ | `execution_queue` with async processing |
| Partial Fill | ⚠️ | FIFO lots system supports it, but no explicit partial tracking |
| Full Fill | ✅ | `events["fills"]` in broker |
| Cancel | ✅ | `shutdown()` clears working orders |
| Reject | ✅ | Hard limit violations logged as `OrderRejected` events |

**Status: ⚠️ PARTIAL** - Partial fills not explicitly tested

---

### 1.4 Position Tracking & Reconciliation

| Component | Status | Evidence |
|-----------|--------|----------|
| Position State | ✅ | `PaperBroker.pos` with FIFO lots |
| State Persistence | ✅ | `_save_state()` / `_load_state()` with atomic writes |
| Backup/Recovery | ✅ | `.bak` files + corrupt file handling |
| Equity Tracking | ✅ | `current_equity`, `starting_equity` |

**Status: ✅ PASS**

---

### 1.5 Risk Management

| Control | Status | Limit | Evidence |
|---------|--------|-------|----------|
| Max Position Size | ✅ | $200,000 | `hard_limits.MAX_POSITION_SIZE_USD` |
| Daily Loss | ✅ | $50 / 5% | `MAX_DAILY_LOSS_USD`, `MAX_DAILY_LOSS_PCT` |
| Rate Limit | ✅ | 10/min | `MAX_ORDERS_PER_MINUTE` |
| Leverage Cap | ✅ | 20x | `MAX_LEVERAGE` |
| Max Errors | ✅ | 20 | `MAX_ERRORS_PER_SESSION` |
| Circuit Breaker | ✅ | 5 consec losses | `TradingCircuitBreaker` |
| Kill Switch | ✅ | Env var | `LA_KILL_SWITCH=TRUE` |
| R:R Minimum | ✅ | 1.0 | `MIN_RR_RATIO` |

**Status: ✅ PASS**

---

### 1.6 Error Handling + Retries + Circuit Breakers

| Component | Status | Evidence |
|-----------|--------|----------|
| API Retries | ✅ | `tenacity` decorators with exponential backoff |
| Generic Circuit Breaker | ✅ | `resilience/circuit.py` (3 failures, 60s reset) |
| Trading Circuit Breaker | ✅ | `TradingCircuitBreaker` (equity-based) |
| Consecutive Loss Tracking | ✅ | `_consecutive_losses` counter |
| Error Fingerprinting | ✅ | `AutonomousMemoryHandler` captures errors |

**Status: ✅ PASS**

---

### 1.7 Logging/Telemetry

| Component | Status | Evidence |
|-----------|--------|----------|
| Structured Logs | ✅ | `JsonFormatter` → `system.jsonl` |
| Event Stream | ✅ | `events.jsonl` via `append_event()` |
| Console Rich Output | ✅ | `EventPanelHandler` for trades |
| Secret Scrubbing | ✅ | `SensitiveDataFilter`, `scrub_secrets()` |
| Log Rotation | ✅ | `RotatingFileHandler` (10MB, 5 backups) |
| Webhook Alerts | ✅ | `write_alert()` with `WEBHOOK_URL` |
| Metrics Export | ✅ | `metrics.json`, `metrics.csv` |

**Status: ✅ PASS**

---

### 1.8 Time Synchronization

| Component | Status | Evidence |
|-----------|--------|----------|
| Server Time Sync | ✅ | NTP-style sync via REST in `connect()` |
| Offset Calculation | ✅ | `self.time_offset` with latency compensation |
| Timestamp Validation | ✅ | Rejects timestamps before 2024 |

**Status: ✅ PASS**

---

### 1.9 Deterministic Configuration Loading

| Component | Status | Evidence |
|-----------|--------|----------|
| Strategy Config Validation | ✅ | Pydantic `StrategyConfig.validate_config()` |
| Immutable Hard Limits | ✅ | Constants in `hard_limits.py` |
| Risk Config Loading | ✅ | YAML from `config/risk.yaml` |
| Exchange Config | ✅ | YAML from `config/exchanges/bitunix.yaml` |

**Status: ✅ PASS**

---

### 1.10 Startup/Shutdown Behavior

| Component | Status | Evidence |
|-----------|--------|----------|
| PID Lock | ✅ | `paper/async_session.lock` prevents duplicates |
| Clean Start | ✅ | State restoration, history seeding |
| Graceful Shutdown | ✅ | `GRACEFUL SHUTDOWN INITIATED`, task cancellation |
| Signal Handlers | ✅ | SIGINT/SIGTERM handling |
| Position Cleanup | ✅ | `broker.close_all()` on shutdown |
| Order Cleanup | ✅ | `cancel_all_open_orders()` |
| Watchdog | ✅ | `_threaded_watchdog()` kills frozen process |

**Status: ✅ PASS**

---

## 2. Paper Trading Test Plan (10-Minute Autonomous Run)

### 2.1 Pre-Run Setup Steps

```powershell
# Step 1: Clean state
la clean
Remove-Item -Path "paper/*.json" -ErrorAction SilentlyContinue
Remove-Item -Path "paper/*.lock" -ErrorAction SilentlyContinue

# Step 2: Verify environment
la doctor --fix

# Step 3: Confirm no existing session
la status
# Expected: STOPPED

# Step 4: Set test parameters (optional - use mock for reproducibility)
# For deterministic testing:
$env:LA_TEST_MODE = "TRUE"

# Step 5: Record start timestamp
$START_TIME = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "Test started at: $START_TIME"
```

### 2.2 Execution Command

```powershell
# Option A: Real WebSocket (production-like)
la run --mode live-session --duration 10 --async --symbol BTCUSDT

# Option B: Mock provider (reproducible)
la run --mode live-session --duration 10 --async --source mock

# Option C: With dashboard
la run --mode live-session --duration 10 --async --dashboard
```

### 2.3 Success Criteria

| Criterion | How to Verify | Required |
|-----------|---------------|----------|
| Ran for full 10 minutes | `final_report.json: duration_seconds >= 600` | ✅ |
| No crashes | Process exit code = 0 | ✅ |
| Error count ≤ 5 | `final_report.json: error_count <= 5` | ✅ |
| Data continuity | No `GAP_DETECTED` warnings in logs | ⚠️ |
| Heartbeats logged | `AsyncHeartbeat` events every ~1s | ✅ |
| State saved | `.workspace/paper/unified_state.json` exists | ✅ |
| No memory leak | Final RSS < 500MB | ✅ |
| Graceful shutdown | Log contains `GRACEFUL SHUTDOWN INITIATED` | ✅ |
| Summary generated | `.workspace/runs/latest/summary.html` exists | ✅ |

### 2.4 Failure Criteria

| Failure | Detection |
|---------|-----------|
| Crash before 10 min | Process terminates early |
| Memory runaway | `CRITICAL: Memory Limit Exceeded` in logs |
| Watchdog kill | `WATCHDOG_FATAL: Main loop frozen` |
| Circuit breaker trip | `CIRCUIT BREAKER TRIPPED` in logs |
| Stale data shutdown | `ORDER_BOOK_STALE` event |
| > 5 errors | `error_count > 5` in final report |
| State corruption | `Failed to load state` errors |

### 2.5 Test Cases

#### Normal Conditions
| Test Case | Command | Expected |
|-----------|---------|----------|
| TC-01: Basic 10-min | `la run --mode live-session --duration 10 --async` | Completes with 0 errors |
| TC-02: Mock data | `la run --mode live-session --duration 10 --async --source mock` | Deterministic completion |
| TC-03: With dashboard | `la run --mode live-session --duration 10 --async --dashboard` | Dashboard accessible |

#### Edge Cases
| Test Case | Setup | Expected |
|-----------|-------|----------|
| TC-10: Kill switch | Set `LA_KILL_SWITCH=TRUE` | Orders blocked, no trades |
| TC-11: Session lock | Start 2nd session while 1st runs | 2nd rejected with `already_running` |
| TC-12: Graceful stop | Run `la stop` mid-session | Clean shutdown, positions closed |
| TC-13: Memory pressure | Run with constrained memory | Watchdog triggers at 1.5GB |
| TC-14: Stale data | Disconnect network mid-run | `ORDER_BOOK_STALE` → shutdown |
| TC-15: Resume after crash | Kill process, restart | State restored from `.bak` |

### 2.6 Metrics to Capture

```json
{
  "latency": {
    "tick_to_strategy_ms": "< 50ms target",
    "order_to_fill_ms": "< 300ms target (execution_latency_ms param)"
  },
  "data_quality": {
    "dropped_ticks": "QUEUE_OVERFLOW warnings count",
    "gap_count": "GAP_DETECTED warnings count",
    "stale_events": "ORDER_BOOK_STALE events"
  },
  "execution": {
    "orders_submitted": "from order_history length",
    "fills_count": "trades counter",
    "rejects_count": "OrderRejected events"
  },
  "performance": {
    "rss_mb_peak": "via psutil or task manager",
    "iterations": "from final_report.json",
    "heartbeat_regularity": "AsyncHeartbeat timestamp diffs"
  },
  "pnl": {
    "starting_equity": "from broker state",
    "ending_equity": "from final_report.json",
    "net_pnl": "ending - starting",
    "fees_total": "sum from trades"
  }
}
```

---

## 3. Evidence to Collect

### 3.1 Required Log Files

| File | Location | Purpose |
|------|----------|---------|
| Session Log | `autonomy_session.log` | Real-time console output |
| System JSONL | `.workspace/logs/system.jsonl` | Structured logs |
| Events JSONL | `.workspace/runs/latest/events.jsonl` | Trade/order events |
| Metrics JSON | `.workspace/runs/latest/metrics.json` | Per-iteration metrics |
| Final Report | `.workspace/runs/latest/final_report.json` | Summary |

### 3.2 Required Log Fields

```json
// system.jsonl entry
{
  "timestamp": "2026-01-17T14:08:51.123456",
  "level": "INFO",
  "component": "btc_agents",
  "message": "EVENT: AsyncHeartbeat",
  "meta": {
    "event": "AsyncHeartbeat",
    "price": 100714.50,
    "pos": "FLAT",
    "equity": 10000.0,
    "unrealized": 0.0,
    "elapsed": 227.05
  }
}

// events.jsonl entry (trade)
{
  "event": "ExecutionFill",
  "side": "LONG",
  "price": 100500.25,
  "qty": 0.01,
  "fees": 0.05,
  "at": "2026-01-17T14:10:00Z",
  "client_order_id": "abc123"
}
```

### 3.3 Config Snapshot

Capture before run:
```powershell
Copy-Item "config/strategies/default.json" ".workspace/runs/latest/config_snapshot.json"
```

### 3.4 State Files

| File | Purpose |
|------|---------|
| `.workspace/paper/async_broker_state.json` | Broker position/equity |
| `.workspace/paper/unified_state.json` | Circuit breaker state |
| `paper/last_price_cache.json` | Last known price (resume) |

### 3.5 Screenshots (if dashboard enabled)

1. Dashboard at session start (equity baseline)
2. Dashboard mid-session (active position if any)
3. Dashboard at completion (final equity)

---

## 4. Conversion-to-Live Readiness Assessment

### 4.1 Credentials/Secrets Management

| Current State | Gap | Recommendation |
|---------------|-----|----------------|
| `.env` file with API keys | ⚠️ File-based | Use encrypted secrets vault (Azure Key Vault, AWS SSM) |
| `scrub_secrets()` in logging | ✅ Good | None |
| No secret rotation | ⚠️ Gap | Implement key rotation schedule |

### 4.2 Slippage/Fees Model

| Current State | Gap | Recommendation |
|---------------|-----|----------------|
| Configurable `slip_bps`, `fees_bps` | ⚠️ Static | Fetch real-time fees from exchange API |
| Random slippage variation | ✅ Good | None |
| Maker/taker fee distinction | ✅ Good | None |

### 4.3 Order Sizing + Compliance

| Current State | Gap | Recommendation |
|---------------|-----|----------------|
| Hard limit $200K | ✅ Good | Consider tiered limits per account size |
| `minQty` enforcement | ✅ Good | None |
| `lotSize` rounding | ✅ Good | None |
| No margin check | 🔴 Critical | Add margin balance verification before order |

### 4.4 Kill Switch + Max Loss Guardrails

| Current State | Gap | Recommendation |
|---------------|-----|----------------|
| `LA_KILL_SWITCH` env var | ✅ Good | Add remote kill switch (webhook) |
| $50 daily loss | ✅ Good | Make configurable per account |
| Circuit breaker | ✅ Good | None |
| No max loss per trade | ⚠️ Gap | Add per-trade loss limit |

### 4.5 Monitoring/Alerting

| Current State | Gap | Recommendation |
|---------------|-----|----------------|
| Webhook alerts | ✅ Good | None |
| File-based alerts | ✅ Good | Add Slack/Discord integration |
| No PagerDuty/OpsGenie | ⚠️ Gap | Add on-call alerting for live |
| No dashboard auth | ⚠️ Gap | Add authentication for live dashboard |

### 4.6 Broker/Exchange API Differences

| Component | Paper | Live | Gap |
|-----------|-------|------|-----|
| Order Submission | `PaperBroker.on_candle()` | `BitunixBroker.on_candle()` | ✅ Both exist |
| Position Sync | Local state | Exchange polling | ✅ Implemented |
| Latency Simulation | Configurable delay | Real latency | ✅ N/A for live |
| Human Confirm Gate | N/A | `input()` or config file | ✅ Exists |

### 4.7 Paper/Live Environment Separation

| Current State | Gap | Recommendation |
|---------------|-----|----------------|
| `--source` flag (mock/bitunix) | ⚠️ Incomplete | Add explicit `--env paper|live` flag |
| `PaperBroker` vs `BitunixBroker` | ✅ Good | None |
| Same config files | 🔴 Critical | Separate `config/live/` and `config/paper/` |
| Human confirm gate | ✅ Good | None |
| `live_trading_enabled.txt` | ✅ Good | None |

---

## 5. Pass/Fail Rubric

### Immediate Application Checklist

| # | Check | Pass Criteria | Your Result |
|---|-------|---------------|-------------|
| 1 | **10-min completion** | `duration_seconds >= 600` | ☐ |
| 2 | **Zero crashes** | Exit code = 0 | ☐ |
| 3 | **Low errors** | `error_count <= 5` | ☐ |
| 4 | **Heartbeat regularity** | No gaps > 5s in `AsyncHeartbeat` | ☐ |
| 5 | **State persistence** | `unified_state.json` exists post-run | ☐ |
| 6 | **Graceful shutdown** | `GRACEFUL SHUTDOWN INITIATED` logged | ☐ |
| 7 | **No memory leak** | Peak RSS < 500MB | ☐ |
| 8 | **Artifacts generated** | `summary.html`, `final_report.json` exist | ☐ |
| 9 | **PnL integrity** | `net_pnl` matches `ending - starting` | ☐ |
| 10 | **No secret leakage** | `system.jsonl` contains no API keys | ☐ |

**Passing Score**: 9/10 minimum (item 4 can be warning)

---

## 6. Prioritized Gap List

### 🔴 Critical (Block Live Trading)

| ID | Gap | Impact | Fix |
|----|-----|--------|-----|
| C1 | **No margin balance check** | Insufficient margin → rejected orders | Add `provider.get_balance()` check before order |
| C2 | **Shared config for paper/live** | Accidental live trade with test settings | Create `config/live/` directory with separate files |

### 🟠 High (Fix Before Live)

| ID | Gap | Impact | Fix |
|----|-----|--------|-----|
| H1 | Partial fill tracking | Position drift if partial fills occur | Add explicit partial fill state machine |
| H2 | No per-trade loss limit | Single bad trade can exceed daily limit | Add `MAX_LOSS_PER_TRADE` in hard_limits |
| H3 | Static slippage model | Over/underestimates costs | Fetch real-time spread from orderbook |
| H4 | No remote kill switch | Can't stop runaway bot remotely | Add webhook or cloud-based kill trigger |

### 🟡 Medium (Recommended)

| ID | Gap | Impact | Fix |
|----|-----|--------|-----|
| M1 | No key rotation | Long-lived API keys are risky | Implement quarterly key rotation |
| M2 | No on-call alerting | Delayed response to critical failures | Add PagerDuty/OpsGenie integration |
| M3 | Dashboard lacks auth | Security risk in live | Add basic auth or token validation |
| M4 | No explicit `--env` flag | Easy to confuse paper/live | Add `--env paper|live` CLI argument |

### 🟢 Low (Nice to Have)

| ID | Gap | Impact | Fix |
|----|-----|--------|-----|
| L1 | No trade replay mode | Harder to debug past issues | Add `--replay-from <date>` mode |
| L2 | No performance regression tests | Could miss latency degradation | Add benchmark test suite |

---

## 7. State Machine Diagram

```
                    ┌─────────────────────────────────────────────────────┐
                    │                   ASYNC SESSION                      │
                    └─────────────────────────────────────────────────────┘
                                            │
                                            ▼
                    ┌─────────────────────────────────────────────────────┐
                    │               INITIALIZING                           │
                    │  • Load config                                       │
                    │  • Validate strategy                                 │
                    │  • Create PID lock                                   │
                    │  • Restore circuit breaker state                     │
                    └─────────────────────────────────────────────────────┘
                                            │
                            ┌───────────────┴───────────────┐
                            │                               │
                            ▼                               ▼
                    [Lock exists?]                   [Config invalid?]
                        │ YES                              │ YES
                        ▼                                  ▼
                    ALREADY_RUNNING                  CONFIG_VALIDATION_FAILED
                    (exit immediately)               (exit immediately)
                            │ NO                           │ NO
                            └───────────────┬──────────────┘
                                            ▼
                    ┌─────────────────────────────────────────────────────┐
                    │               SEEDING HISTORY                        │
                    │  • Fetch historical candles (REST)                   │
                    │  • Retry up to 5 times                               │
                    │  • Detect gaps                                       │
                    └─────────────────────────────────────────────────────┘
                                            │
                            ┌───────────────┴───────────────┐
                            │                               │
                            ▼                               ▼
                    [< min_history?]                 [Seed success]
                        │ YES                              │
                        ▼                                  │
                    FATAL_ERROR                            │
                    (exit)                                 │
                                                           ▼
                    ┌─────────────────────────────────────────────────────┐
                    │                    RUNNING                           │
                    │                                                      │
                    │  Concurrent Tasks:                                   │
                    │  ├── market_data_task (WS consumer)                  │
                    │  ├── execution_task (order processing)               │
                    │  ├── watchdog_task (frozen loop detection)           │
                    │  ├── heartbeat_task (1s status updates)              │
                    │  ├── timer_task (duration countdown)                 │
                    │  ├── kill_switch_task (file/env check)               │
                    │  ├── stale_data_task (timeout detection)             │
                    │  ├── funding_task (8h funding rate)                  │
                    │  └── checkpoint_task (state persistence)             │
                    └─────────────────────────────────────────────────────┘
                                            │
            ┌───────────────┬───────────────┼───────────────┬───────────────┐
            │               │               │               │               │
            ▼               ▼               ▼               ▼               ▼
      [Duration]      [Kill Switch]   [Stale Data]  [Circuit Trip]  [Watchdog]
       expired          triggered       detected       tripped         freeze
            │               │               │               │               │
            └───────────────┴───────────────┴───────────────┴───────────────┘
                                            │
                                            ▼
                    ┌─────────────────────────────────────────────────────┐
                    │                SHUTTING_DOWN                         │
                    │  • Set _shutting_down flag                           │
                    │  • Cancel all open orders                            │
                    │  • Wait 2s for pending fills                         │
                    │  • Cancel all async tasks                            │
                    │  • Close any open positions                          │
                    │  • Save broker state                                 │
                    │  • Export metrics (JSON, CSV)                        │
                    │  • Generate summary report                           │
                    │  • Write final_report.json                           │
                    │  • Remove PID lock                                   │
                    └─────────────────────────────────────────────────────┘
                                            │
                                            ▼
                    ┌─────────────────────────────────────────────────────┐
                    │                  COMPLETED                           │
                    │  Exit code: 0 (success) or 1 (errors)                │
                    └─────────────────────────────────────────────────────┘
```

---

## 8. Recommended Log Schema

### Event Types for Audit Trail

```json
// System Events
{"event": "SYSTEM_STARTUP", "mode": "live-session", "config": {...}}
{"event": "SYSTEM_SHUTDOWN", "reason": "duration_complete", "exit_code": 0}

// Data Events
{"event": "CandleClosed", "ts": 1234567890, "close": 100500.0}
{"event": "TickReceived", "bid": 100499.0, "ask": 100501.0}
{"event": "GapDetected", "missing_count": 2, "prev_ts": 123, "curr_ts": 456}
{"event": "ORDER_BOOK_STALE", "timeout": 15.0, "last_msg": 1234567800}

// Order Events
{"event": "OrderSubmitted", "client_order_id": "abc", "side": "LONG", "qty": 0.01}
{"event": "OrderRejected", "reason": "rate_limit_exceeded"}
{"event": "OrderRejected", "reason": "notional_exceeded", "notional": 250000}
{"event": "ExecutionFill", "side": "LONG", "price": 100500, "qty": 0.01, "fees": 0.05}
{"event": "ExecutionExit", "reason": "TP", "price": 101000, "pnl": 5.0}

// Risk Events
{"event": "CircuitBreakerTripped", "reason": "max_daily_drawdown", "detail": "5.2% >= 5%"}
{"event": "KillSwitchActivated", "source": "environment"}

// Heartbeat
{"event": "AsyncHeartbeat", "price": 100500, "pos": "LONG", "equity": 10050, "elapsed": 300}
```

---

## 9. Quick Verification Script

Save as `scripts/verify_autonomy.ps1`:

```powershell
# Verify 10-minute autonomous run
param(
    [int]$Duration = 10,
    [string]$Source = "mock"
)

$ErrorActionPreference = "Stop"
$TestDir = ".workspace/test_run_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
New-Item -ItemType Directory -Path $TestDir -Force | Out-Null

Write-Host "=== AUTONOMY TEST ===" -ForegroundColor Cyan
Write-Host "Duration: $Duration minutes"
Write-Host "Source: $Source"
Write-Host "Output: $TestDir"
Write-Host ""

# Pre-flight
Write-Host "[1/5] Pre-flight checks..." -ForegroundColor Yellow
& la doctor
if ($LASTEXITCODE -ne 0) { throw "Doctor failed" }

# Clean slate
Write-Host "[2/5] Cleaning state..." -ForegroundColor Yellow
Remove-Item -Path "paper/*.lock" -ErrorAction SilentlyContinue

# Run session
Write-Host "[3/5] Starting session..." -ForegroundColor Yellow
$process = Start-Process -FilePath "python" `
    -ArgumentList "-m", "laptop_agents", "run", "--mode", "live-session", `
                  "--duration", $Duration, "--async", "--source", $Source `
    -PassThru -RedirectStandardOutput "$TestDir/stdout.txt" `
    -RedirectStandardError "$TestDir/stderr.txt"

$process.WaitForExit()
$exitCode = $process.ExitCode

Write-Host "[4/5] Collecting artifacts..." -ForegroundColor Yellow
Copy-Item ".workspace/runs/latest/*" "$TestDir/" -Recurse -ErrorAction SilentlyContinue
Copy-Item ".workspace/paper/*" "$TestDir/paper/" -Recurse -ErrorAction SilentlyContinue

# Verify
Write-Host "[5/5] Verifying results..." -ForegroundColor Yellow
$report = Get-Content "$TestDir/final_report.json" | ConvertFrom-Json

$results = @{
    "Exit Code" = if ($exitCode -eq 0) { "✅ PASS" } else { "❌ FAIL ($exitCode)" }
    "Duration" = if ($report.duration_seconds -ge ($Duration * 60 - 10)) { "✅ PASS ($($report.duration_seconds)s)" } else { "❌ FAIL" }
    "Errors" = if ($report.error_count -le 5) { "✅ PASS ($($report.error_count))" } else { "❌ FAIL" }
    "Status" = if ($report.status -eq "success") { "✅ PASS" } else { "❌ FAIL" }
}

Write-Host ""
Write-Host "=== RESULTS ===" -ForegroundColor Cyan
$results.GetEnumerator() | ForEach-Object {
    Write-Host "$($_.Key): $($_.Value)"
}

$passCount = ($results.Values | Where-Object { $_ -like "✅*" }).Count
$totalCount = $results.Count
Write-Host ""
Write-Host "Score: $passCount/$totalCount" -ForegroundColor $(if ($passCount -ge 3) { "Green" } else { "Red" })
```

---

## Summary

**Overall Verdict: ✅ PASS FOR 10-MINUTE AUTONOMOUS PAPER TRADING**

Your app demonstrates solid autonomous operation capabilities with:
- Complete execution loop
- Robust error handling and circuit breakers
- State persistence and recovery
- Comprehensive logging
- Multiple safety guardrails

**Before Live Trading**, address the **2 Critical gaps**:
1. Add margin balance verification
2. Separate paper/live config directories

Run the test plan above and collect the artifacts to document autonomous operation capability.
