# QA Autonomy Audit Prompt for BTC Laptop Agents

> Use this prompt to evaluate whether the system can paper trade fully autonomously for 10 continuous minutes and assess live-trading readiness.

---

You are an expert QA engineer + trading-systems architect. Your job is to evaluate whether BTC Laptop Agents can paper trade fully autonomously for 10 continuous minutes using its built-in strategy (`config/strategies/default.json`), and whether it can be safely converted to live trading via `BitunixBroker`.

## System Overview (Pre-Loaded Context)

- **CLI Entrypoint**: `la` command (`python -m laptop_agents`)
- **Autonomous Mode**: `la run --mode live-session --duration 10 --async`
- **Paper Broker**: `src/laptop_agents/paper/broker.py` (PaperBroker)
- **Live Broker**: `src/laptop_agents/execution/bitunix_broker.py` (BitunixBroker)
- **Async Session Loop**: `src/laptop_agents/session/async_session.py` (AsyncRunner)
- **Circuit Breaker**: `src/laptop_agents/resilience/trading_circuit_breaker.py`
- **Data Provider**: `src/laptop_agents/data/providers/bitunix_ws.py` (WebSocket)
- **Strategy Config**: `config/strategies/default.json`
- **Risk Config**: `config/risk.yaml`
- **Artifacts Dir**: `.workspace/runs/latest/`
- **Kill Switch**: `LA_KILL_SWITCH=TRUE` env variable or `kill.txt` file
- **Hard Limits**: $50 max daily loss, $200K max position, 1% max risk per trade

---

## Your Tasks

### 1. Autonomy Verification Checklist

Create a checklist proving the app can run unattended for 10 minutes. Verify each component:

| Component | Key Files | What to Verify |
|-----------|-----------|----------------|
| **Strategy Execution Loop** | `async_session.py`, `agents/supervisor.py` | Signal → Decision → Order → Monitor → Exit lifecycle |
| **Market Data Stream** | `data/providers/bitunix_ws.py` | WebSocket stability, reconnect logic, stale data detection (`stale_data_timeout_sec`) |
| **Order Lifecycle** | `paper/broker.py`, `execution/bitunix_broker.py` | Fill simulation, position tracking, state persistence |
| **Position Reconciliation** | `PaperBroker.on_candle()` | Entry/exit detection, PnL calculation, equity updates |
| **Risk Management** | `trading_circuit_breaker.py`, `core/hard_limits.py` | Max drawdown (5%), consecutive loss limit (5), daily loss ($50) |
| **Error Handling** | `resilience/retry.py`, `resilience/circuit.py`, `resilience/rate_limiter.py` | Retries, circuit breakers, backoff |
| **Logging/Telemetry** | `core/logger.py`, `core/orchestrator.py` | `events.jsonl`, `system.jsonl`, `summary.html` |
| **Watchdog** | `AsyncRunner._threaded_watchdog()` | Heartbeat check (30s freeze detection), memory limit (1.5GB) |
| **Config Loading** | `core/config_models.py` | `StrategyConfig.validate_config()` on startup |
| **Startup/Shutdown** | `async_session.py`, `la stop` | PID lock (`paper/async_session.lock`), graceful SIGTERM handling, `close_all()` |

---

### 2. Paper Trading Test Plan (10-Minute Autonomous Run)

#### Pre-Run Setup

```powershell
# 1. Verify environment
la doctor --fix

# 2. Clear previous state (optional, for clean test)
la clean
Remove-Item .workspace/paper/* -Force -ErrorAction SilentlyContinue

# 3. Verify config is valid
cat config/strategies/default.json

# 4. Check no session is already running
la status
# Expected: STOPPED
```

#### Execution

```powershell
# Run 10-minute autonomous session with mock data (no network dependency)
la run --mode live-session --duration 10 --source mock --async

# OR with real Bitunix WebSocket data
la run --mode live-session --duration 10 --async --dashboard
```

#### Success Criteria (ALL must be true)

- [ ] Session ran for full 10 minutes without human intervention
- [ ] Exit reason is `completed` (not `error`, `circuit_breaker`, `stale_data`)
- [ ] No `CRITICAL` or `FATAL` entries in `.workspace/runs/latest/system.jsonl`
- [ ] `.workspace/runs/latest/summary.html` exists and is viewable
- [ ] If trades occurred: `trades.csv` contains valid entries with `entry_price`, `exit_price`, `pnl`
- [ ] Ending equity matches calculated PnL (no drift)
- [ ] PID lock file (`paper/async_session.lock`) was cleaned up

#### Failure Criteria (ANY indicates not autonomous/safe)

- [ ] Process crashed or was killed by watchdog
- [ ] `stale_data` shutdown due to WebSocket dropout > 30s
- [ ] `FatalError` from WebSocket provider without recovery
- [ ] Circuit breaker tripped unexpectedly (check `events.jsonl` for `CIRCUIT_BREAKER_TRIPPED`)
- [ ] Memory exceeded 1.5GB (watchdog kill)
- [ ] Heartbeat freeze > 30s detected
- [ ] Strategy config validation failed on startup
- [ ] Lock file still exists after session ended

#### Edge Case Tests

| Test Case | How to Trigger | Expected Behavior |
|-----------|----------------|-------------------|
| Kill switch | Set `LA_KILL_SWITCH=TRUE` or create `kill.txt` | Immediate graceful shutdown, positions closed |
| Stale data | Use mock provider, inject 35s gap | Shutdown with `stopped_reason: stale_data` |
| Circuit breaker | Inject 5 consecutive losing trades | Trips, halts trading, logs reason |
| SIGTERM | Send `Ctrl+C` or `taskkill` | Graceful shutdown, `close_all()` called |
| Memory pressure | (manual monitoring) | Watchdog kills at 1.5GB |

---

### 3. Evidence to Collect

#### Required Artifacts

| Artifact | Location | Required Fields/Content |
|----------|----------|------------------------|
| **Session Log** | `.workspace/runs/latest/system.jsonl` | `timestamp`, `level`, `message`, `component` |
| **Event Stream** | `.workspace/runs/latest/events.jsonl` | `event` type, `timestamp`, order/fill/exit details |
| **Trade Blotter** | `.workspace/runs/latest/trades.csv` | `entry_ts`, `exit_ts`, `side`, `entry_price`, `exit_price`, `qty`, `pnl` |
| **HTML Report** | `.workspace/runs/latest/summary.html` | Readable, shows final equity, trade count |
| **Config Snapshot** | (capture before run) | Full `default.json` content |
| **Broker State** | `.workspace/paper/async_broker_state.json` | `positions`, `equity`, `trades` |
| **Circuit Breaker State** | (via `StateManager`) | `tripped`, `reason`, `consecutive_losses` |

#### Key Log Fields to Verify

```json
// Expected event types in events.jsonl:
{"event": "SessionStart", "timestamp": "...", "duration_min": 10}
{"event": "CandleProcessed", "timestamp": "...", "close": 95000.0}
{"event": "SignalGenerated", "signal": "LONG", "..."}
{"event": "OrderSubmitted", "side": "BUY", "qty": 0.01}
{"event": "ExecutionFill", "side": "BUY", "price": 95000.0}
{"event": "ExecutionExit", "reason": "take_profit", "pnl": 15.0}
{"event": "SessionEnd", "stopped_reason": "completed"}
```

---

### 4. Conversion-to-Live Readiness Assessment

Identify what must change to convert from `PaperBroker` to `BitunixBroker`:

| Area | Current State | Required for Live |
|------|---------------|-------------------|
| **Credentials** | `.env` with `BITUNIX_API_KEY/SECRET` | Verify secrets not logged, rotation plan |
| **Slippage/Fees** | Configurable via `fees_bps`, `slip_bps` | Calibrate to real Bitunix fees (maker/taker) |
| **Order Sizing** | `config/risk.yaml` limits | Add exchange-specific min/max order checks |
| **Kill Switch** | `LA_KILL_SWITCH` env var + `kill.txt` | Add monitoring alert when triggered |
| **Max Loss Guardrails** | Hard-coded $50/day in `hard_limits.py` | Review if appropriate for live capital |
| **Monitoring/Alerting** | Logs only | Add `src/laptop_agents/alerts/` integration (email/Slack) |
| **Broker Shutdown** | `BitunixBroker.shutdown()` | Verify cancels all orders, closes positions |
| **Paper/Live Separation** | `config/live_trading_enabled.txt` | Ensure explicit opt-in required |
| **State Isolation** | `.workspace/paper/` for paper | Separate live state directory |

#### Critical Pre-Live Checks

- [ ] `BitunixBroker.shutdown()` tested with real API (sandbox if available)
- [ ] Rate limits enforced (`resilience/rate_limiter.py`)
- [ ] No accidental live orders possible without explicit flag
- [ ] Secrets never appear in logs/artifacts
- [ ] Recovery from API errors tested (order reject, insufficient balance)

---

### 5. Deliverables Format

#### Pass/Fail Rubric

| Category | Pass | Fail |
|----------|------|------|
| **10-Min Autonomy** | Full run, no intervention, `completed` exit | Crash, watchdog kill, or manual intervention |
| **Data Stability** | No stale data shutdowns | WebSocket failures > 30s |
| **Risk Controls** | Circuit breaker functional, limits enforced | Limits bypassed or non-functional |
| **Logging** | All required artifacts generated | Missing events.jsonl or summary.html |
| **Shutdown** | Clean exit, no orphan processes | Lock file remains, PID still running |
| **Live Readiness** | All "Required for Live" items addressed | Critical gaps remain |

#### Gap Prioritization

| Priority | Definition | Example |
|----------|------------|---------|
| **Critical** | Blocks autonomous operation or live trading | No circuit breaker, no kill switch |
| **High** | Significant risk or reliability issue | No reconnect logic, no state persistence |
| **Medium** | Operational concern | Missing alerts, incomplete logs |
| **Low** | Polish/enhancement | Better dashboard metrics |

---

## Important Constraints

- Do NOT implement trading strategies or provide financial advice
- Focus strictly on system capability, safety, and testability
- Assume this must work without human intervention for the full 10 minutes
- All file paths are relative to repo root: `c:/Users/lovel/trading/btc-laptop-agents/`

---

## Begin Evaluation

Start by running:
```powershell
la doctor --fix
la run --mode live-session --duration 10 --source mock --async
```

Then collect artifacts and evaluate against the rubric above.
