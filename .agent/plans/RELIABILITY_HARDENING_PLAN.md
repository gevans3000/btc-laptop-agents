# Reliability Hardening Plan
## Autonomous Execution Plan for Gemini 3 Flash

**Created**: 2026-01-15
**Objective**: Harden the `btc-laptop-agents` Live Trading System for 10+ minute unattended operation.
**Execution Mode**: Fully autonomous. All commands use `SafeToAutoRun: true`.

---

## Pre-Execution Setup

```powershell
# // turbo-all
cd c:\Users\lovel\trading\btc-laptop-agents
$env:PYTHONPATH = "c:\Users\lovel\trading\btc-laptop-agents\src"
.\.venv\Scripts\Activate.ps1
```

**Verify Environment**:
```powershell
python -c "from laptop_agents.session.async_session import AsyncRunner; print('OK')"
```
If this fails, abort and report the import error.

---

## Phase 1: Critical Fixes (Must Do)

### 1.1 WebSocket Error Propagation (IMPROVE)
**File**: `src/laptop_agents/session/async_session.py`
**Current**: Errors logged but session stays alive deaf.
**Change**: Add consecutive error counter; shutdown after 3 WS failures.

```python
# In AsyncRunner.__init__, add:
self.consecutive_ws_errors: int = 0
self.max_ws_errors: int = 3

# In market_data_task, replace the except block (lines ~183-185):
except Exception as e:
    logger.error(f"Error in market_data_task: {e}")
    self.consecutive_ws_errors += 1
    self.errors += 1
    if self.consecutive_ws_errors >= self.max_ws_errors:
        logger.error(f"WS_FATAL: {self.max_ws_errors} consecutive errors. Triggering shutdown.")
        self.shutdown_event.set()
```

**Verify**: `grep -n "consecutive_ws_errors" src/laptop_agents/session/async_session.py` returns matches.

---

### 1.2 Kill Switch Absolute Path (FIX)
**File**: `src/laptop_agents/session/async_session.py`
**Current**: `self.kill_file = Path("kill.txt")` is relative to CWD.
**Change**: Use repo-root absolute path.

```python
# Line ~83, replace:
self.kill_file = Path("kill.txt")
# With:
self.kill_file = Path(__file__).resolve().parent.parent.parent.parent / "kill.txt"
```

**Verify**: `python -c "from pathlib import Path; p = Path(__file__).resolve().parent.parent.parent.parent / 'kill.txt'; print(p)"` from `src/laptop_agents/session/` prints the repo root.

---

### 1.3 Working Order Expiration (FIX)
**File**: `src/laptop_agents/paper/broker.py`
**Current**: Working orders persist indefinitely.
**Change**: Add 24-hour expiration on load.

```python
# In _load_state (after line ~408), add:
# Expire stale working orders (> 24 hours old)
now = time.time()
self.working_orders = [
    o for o in self.working_orders 
    if now - o.get("created_at", now) < 86400  # 24 hours
]
if len(state.get("working_orders", [])) != len(self.working_orders):
    logger.info(f"Expired {len(state.get('working_orders', [])) - len(self.working_orders)} stale working orders")
```

**Verify**: Unit test or manual check that orders with `created_at` > 24h ago are filtered out.

---

### 1.4 Preflight Exchange Connectivity (IMPROVE)
**File**: `src/laptop_agents/core/preflight.py`
**Current**: Network check exists (line 37-42).
**Status**: ✅ ALREADY DONE. The `urllib.request.urlopen` call to Bitunix is present.
**Action**: SKIP THIS ITEM.

---

### 1.5 Graceful Strategy Agent Degradation (FIX)
**File**: `src/laptop_agents/session/async_session.py`
**Current**: Exception in `on_candle_closed` increments error count but doesn't isolate agent failures.
**Change**: Wrap the Supervisor call in its own try/except.

```python
# In on_candle_closed (around line ~248-260), wrap the Supervisor block:
if self.strategy_config:
    try:
        from laptop_agents.agents.supervisor import Supervisor
        from laptop_agents.agents.state import State as AgentState
        
        supervisor = Supervisor(provider=None, cfg=self.strategy_config, broker=self.broker)
        state = AgentState(instrument=self.symbol, timeframe=self.interval, candles=self.candles[:-1])
        state = supervisor.step(state, candle, skip_broker=True)
        
        if state.setup.get("side") in ["LONG", "SHORT"]:
            raw_signal = "BUY" if state.setup["side"] == "LONG" else "SELL"
    except Exception as agent_err:
        logger.error(f"AGENT_ERROR: Strategy agent failed, skipping signal: {agent_err}")
        from laptop_agents.core.orchestrator import append_event
        append_event({"event": "AgentError", "error": str(agent_err)}, paper=True)
        raw_signal = None  # Suppress trade on agent failure
```

**Verify**: `grep -n "AGENT_ERROR" src/laptop_agents/session/async_session.py` returns a match.

---

## Phase 2: Improve Defaults (Should Do)

### 2.1 Stale-Data Timeout (IMPROVE)
**File**: `src/laptop_agents/session/async_session.py`
**Current**: Default is 30s (line ~47 in `__init__` and line ~85).
**Change**: Increase default to 60s for weekend resilience; CLI already supports `--stale-timeout`.

```python
# Line ~47 and ~85, change default from 30 to 60:
stale_timeout: int = 60,
# and
self.stale_data_timeout_sec: float = float(stale_timeout)  # Already correct
```

Also update the CLI default in `run.py` (line 52):
```python
ap.add_argument("--stale-timeout", type=int, default=60, help="Seconds before stale data triggers shutdown")
```

**Verify**: `python -m src.laptop_agents.run --help | findstr stale-timeout` shows `default: 60`.

---

### 2.2 MAX_ERRORS_PER_SESSION Scaling (IMPROVE)
**File**: `src/laptop_agents/core/hard_limits.py`
**Current**: Fixed at 10.
**Change**: Make it scale with duration or increase to 20.

```python
# In hard_limits.py, change:
MAX_ERRORS_PER_SESSION = 10
# To:
MAX_ERRORS_PER_SESSION = 20  # Reasonable for 10-minute runs
```

Alternatively, for dynamic scaling, modify `async_session.py` to use `max(10, duration_min * 2)`.

**Verify**: `grep MAX_ERRORS_PER_SESSION src/laptop_agents/core/hard_limits.py` shows 20.

---

### 2.3 Watchdog Restart Delay Parameter (IMPROVE)
**File**: `scripts/watchdog.ps1`
**Current**: Fixed `Start-Sleep -Seconds 10`.
**Change**: Add `-RestartDelay` parameter.

```powershell
# Add to param block (after line 13):
[int]$RestartDelay = 10

# Change line 45 from:
Start-Sleep -Seconds 10
# To:
Start-Sleep -Seconds $RestartDelay
```

**Verify**: `.\scripts\watchdog.ps1 -RestartDelay 5` uses 5s delay (manual test).

---

## Phase 3: Already Done / Skip

These items are already implemented or acceptable as-is:

| Item | Status | Reason |
|------|--------|--------|
| Circuit breaker state restoration | ✅ DONE | `async_session.py` L99-107 restores from StateManager |
| Idempotency persistence | ✅ DONE | `processed_order_ids` saved in `broker_state.json` |
| CancelledError handling | ✅ DONE | All async tasks catch it |
| Symbol normalization | ✅ DONE | `run.py` L58 and `bitunix_ws.py` L39-41 normalize |
| Preflight connectivity | ✅ DONE | `preflight.py` L37-42 checks Bitunix |

---

## Phase 4: Deferred / Low Priority

These require more substantial changes and can be done in a future iteration:

| Item | Reason to Defer |
|------|-----------------|
| Event/state atomic persistence | Requires temp-file-swap pattern; current system is acceptable for paper trading |
| Position sync on live startup | Requires additional API call and reconciliation logic; paper mode doesn't need it |
| REST/WS retry coordination | Current tenacity retries are sufficient; edge case |
| Health-check endpoint | Only needed for K8s/Docker deployment; add when containerizing |

---

## Verification Protocol

After all changes, run:

```powershell
# // turbo
cd c:\Users\lovel\trading\btc-laptop-agents
$env:PYTHONPATH = "c:\Users\lovel\trading\btc-laptop-agents\src"
.\.venv\Scripts\Activate.ps1

# 1. Syntax check
python -m py_compile src/laptop_agents/session/async_session.py
python -m py_compile src/laptop_agents/paper/broker.py
python -m py_compile src/laptop_agents/core/hard_limits.py

# 2. Unit tests
pytest tests/ -x -q --tb=short

# 3. Smoke test (10-second mock run)
python -m src.laptop_agents.run --mode live-session --async --source mock --duration 1
```

**Success Criteria**:
- All `py_compile` commands exit 0.
- `pytest` shows no failures.
- Smoke test runs for ~60s and exits with code 0.

---

## Commit Protocol

After verification passes:

```powershell
git add -A
git commit -m "fix(reliability): harden async session for autonomous operation

- Add consecutive WS error counter (shutdown after 3)
- Use absolute path for kill.txt
- Expire stale working orders after 24h
- Wrap supervisor agent in try/except for graceful degradation
- Increase stale-timeout default to 60s
- Scale MAX_ERRORS_PER_SESSION to 20
- Add RestartDelay param to watchdog.ps1"

git push origin main
```

---

## Self-Correction Rules

1. **Import Error**: If any `py_compile` fails, read the error, fix the syntax, and retry.
2. **Test Failure**: If `pytest` fails, read the failing test output, apply the fix, and re-run.
3. **Smoke Test Crash**: If the 1-minute smoke test fails, capture `logs/system.jsonl` last 20 lines and diagnose.

**Do not proceed to commit if verification fails. Fix and re-verify.**

---

## Execution Summary

| Phase | Items | Estimated Time |
|-------|-------|----------------|
| Phase 1 (Critical) | 4 fixes | 10 min |
| Phase 2 (Defaults) | 3 improvements | 5 min |
| Phase 3 (Skip) | 5 items | 0 min |
| Verification | - | 5 min |
| **Total** | **7 changes** | **~20 min** |

---

**END OF PLAN**
