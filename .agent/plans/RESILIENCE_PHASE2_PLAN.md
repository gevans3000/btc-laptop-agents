# Resilience Phase 2 Implementation Plan

**Target Repository**: `c:\Users\lovel\trading\btc-laptop-agents`
**Objective**: Complete remaining reliability and production-readiness features for 10-minute autonomous trading.
**Execution Mode**: Fully autonomous. No human input required.

---

## Pre-Conditions (Verify First)

Before starting, verify:
1. Virtual environment exists: `.venv/Scripts/python.exe`
2. Tests pass: Run `python -m pytest tests/ -x -q -p no:cacheprovider`
3. Previous commit exists: `git log -1 --oneline` shows reliability bundle commit

If any pre-condition fails, STOP and report the failure.

---

## Phase 1: Atomic State Persistence (fsync/WAL)

**Goal**: Prevent journal corruption on crash by flushing writes to disk.

### Task 1.1: Add fsync to append_event

**File**: `src/laptop_agents/core/orchestrator.py`

**Find** `append_event` function and update the file writes:
```python
def append_event(obj: Dict[str, Any], paper: bool = False) -> None:
    obj.setdefault("timestamp", utc_ts())
    event_name = obj.get("event", "UnnamedEvent")
    logger.info(f"EVENT: {event_name}", obj)
    
    if paper:
        PAPER_DIR.mkdir(exist_ok=True)
        with (PAPER_DIR / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
    else:
        with (LATEST_DIR / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
```

### Verification 1:
```powershell
python -c "import ast; ast.parse(open('src/laptop_agents/core/orchestrator.py').read()); print('Syntax OK')"
```

---

## Phase 2: Configurable Stale Data Timeout

**Goal**: Make stale data threshold configurable via CLI.

### Task 2.1: Add CLI argument

**File**: `src/laptop_agents/run.py`

Add after other arguments:
```python
ap.add_argument("--stale-timeout", type=int, default=30, help="Seconds before stale data triggers shutdown")
```

### Task 2.2: Pass to AsyncRunner

**File**: `src/laptop_agents/run.py`

Update `run_async_session` call to include:
```python
stale_timeout=args.stale_timeout,
```

### Task 2.3: Update AsyncRunner

**File**: `src/laptop_agents/session/async_session.py`

Update `run_async_session` signature and `AsyncRunner.__init__`:
```python
async def run_async_session(
    ...
    stale_timeout: int = 30,
) -> AsyncSessionResult:
```

And in `AsyncRunner.__init__`:
```python
self.stale_data_timeout_sec: float = float(stale_timeout)
```

### Verification 2:
```powershell
python -m src.laptop_agents.run --help | Select-String "stale-timeout"
```

---

## Phase 3: Order Rejection Event Logging

**Goal**: Log rejected orders to events.jsonl for debugging.

### Task 3.1: Add OrderRejected event

**File**: `src/laptop_agents/paper/broker.py`

At each rejection point in `_try_fill`, add:
```python
from laptop_agents.core.orchestrator import append_event

# After idempotency rejection:
append_event({"event": "OrderRejected", "reason": "duplicate_order_id", "order_id": client_order_id}, paper=True)

# After throttle rejection:
append_event({"event": "OrderRejected", "reason": "throttled", "seconds_since_last": now - self.last_trade_time}, paper=True)

# After rate limit rejection:
append_event({"event": "OrderRejected", "reason": "rate_limit_exceeded"}, paper=True)

# After daily loss rejection:
append_event({"event": "OrderRejected", "reason": "daily_loss_exceeded", "drawdown_pct": drawdown_pct}, paper=True)

# After notional rejection:
append_event({"event": "OrderRejected", "reason": "notional_exceeded", "notional": notional}, paper=True)

# After leverage rejection:
append_event({"event": "OrderRejected", "reason": "leverage_exceeded", "leverage": leverage}, paper=True)
```

### Verification 3:
```powershell
python -c "from laptop_agents.paper.broker import PaperBroker; print('Import OK')"
```

---

## Phase 4: Trail Activation Event

**Goal**: Log when trailing stop is activated.

### Task 4.1: Add TrailActivated event

**File**: `src/laptop_agents/paper/broker.py`

In `_check_exit`, after `p.trail_active = True`, add:
```python
append_event({
    "event": "TrailActivated",
    "side": p.side,
    "entry": p.entry,
    "trail_stop": p.trail_stop,
    "current_price": float(candle.close)
}, paper=True)
```

### Verification 4:
```powershell
python -m pytest tests/test_safety.py -v --tb=short -p no:cacheprovider
```

---

## Phase 5: Error Budget Tracking

**Goal**: Shutdown session if too many errors occur.

### Task 5.1: Add max_errors config

**File**: `src/laptop_agents/core/hard_limits.py`

Add:
```python
MAX_ERRORS_PER_SESSION = 10
```

### Task 5.2: Enforce in AsyncRunner

**File**: `src/laptop_agents/session/async_session.py`

In `on_candle_closed` exception handler:
```python
except Exception as e:
    logger.error(f"Error in on_candle_closed: {e}")
    self.errors += 1
    if self.errors >= hard_limits.MAX_ERRORS_PER_SESSION:
        logger.error(f"ERROR BUDGET EXHAUSTED: {self.errors} errors. Shutting down.")
        self.shutdown_event.set()
```

Add import at top:
```python
from laptop_agents.core import hard_limits
```

### Verification 5:
```powershell
python -c "from laptop_agents.core.hard_limits import MAX_ERRORS_PER_SESSION; print(f'Limit: {MAX_ERRORS_PER_SESSION}')"
```

---

## Phase 6: Position Age Alert

**Goal**: Warn if position is open too long.

### Task 6.1: Add StalePosition event

**File**: `src/laptop_agents/paper/broker.py`

In `_check_exit`, after `self.pos.bars_open += 1` (in `on_candle`):
```python
if self.pos.bars_open > 50:
    logger.warning(f"STALE POSITION: Open for {self.pos.bars_open} bars")
    append_event({
        "event": "StalePosition",
        "bars_open": self.pos.bars_open,
        "side": self.pos.side,
        "entry": self.pos.entry
    }, paper=True)
```

### Verification 6:
```powershell
python -c "import ast; ast.parse(open('src/laptop_agents/paper/broker.py').read()); print('Syntax OK')"
```

---

## Phase 7: Candle Gap Detection

**Goal**: Detect and log missing candles in data stream.

### Task 7.1: Add gap detection

**File**: `src/laptop_agents/trading/helpers.py`

Add function:
```python
def detect_candle_gaps(candles: List[Candle], interval: str = "1m") -> List[dict]:
    """Detect gaps in candle sequence."""
    if len(candles) < 2:
        return []
    
    interval_seconds = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}.get(interval, 60)
    gaps = []
    
    for i in range(1, len(candles)):
        try:
            prev_ts = int(candles[i-1].ts) if str(candles[i-1].ts).isdigit() else 0
            curr_ts = int(candles[i].ts) if str(candles[i].ts).isdigit() else 0
            if prev_ts > 0 and curr_ts > 0:
                expected_gap = interval_seconds
                actual_gap = curr_ts - prev_ts
                if actual_gap > expected_gap * 1.5:  # Allow 50% tolerance
                    missing = (actual_gap // interval_seconds) - 1
                    gaps.append({
                        "prev_ts": prev_ts,
                        "curr_ts": curr_ts,
                        "missing_count": int(missing)
                    })
        except (ValueError, TypeError):
            continue
    
    return gaps
```

### Task 7.2: Use in async_session

**File**: `src/laptop_agents/session/async_session.py`

In `run()` after seeding candles:
```python
from laptop_agents.trading.helpers import detect_candle_gaps

gaps = detect_candle_gaps(self.candles, self.interval)
for gap in gaps:
    logger.warning(f"GAP_DETECTED: {gap['missing_count']} missing between {gap['prev_ts']} and {gap['curr_ts']}")
```

### Verification 7:
```powershell
python -c "from laptop_agents.trading.helpers import detect_candle_gaps; print('Import OK')"
```

---

## Phase 8: Broker Shutdown Timeout

**Goal**: Prevent hung shutdown.

### Task 8.1: Add timeout wrapper

**File**: `src/laptop_agents/session/async_session.py`

Replace `self.broker.shutdown()` with:
```python
try:
    await asyncio.wait_for(asyncio.to_thread(self.broker.shutdown), timeout=5.0)
except asyncio.TimeoutError:
    logger.error("Broker shutdown timed out after 5s")
```

### Verification 8:
```powershell
python -c "import ast; ast.parse(open('src/laptop_agents/session/async_session.py').read()); print('Syntax OK')"
```

---

## Phase 9: Preflight Check Command

**Goal**: Validate system readiness before trading.

### Task 9.1: Add preflight mode

**File**: `src/laptop_agents/run.py`

Add argument:
```python
ap.add_argument("--preflight", action="store_true", help="Run system readiness checks")
```

Add handler before mode dispatch:
```python
if args.preflight:
    from laptop_agents.core.preflight import run_preflight_checks
    success = run_preflight_checks(args)
    return 0 if success else 1
```

### Task 9.2: Create preflight module

**File**: `src/laptop_agents/core/preflight.py` (NEW)

```python
"""System preflight checks for deployment readiness."""
import os
import json
from pathlib import Path
from laptop_agents.core.logger import logger

def run_preflight_checks(args) -> bool:
    """Run all preflight checks. Returns True if all pass."""
    checks = []
    
    # 1. Environment variables
    if args.mode in ["live", "live-session"]:
        api_key = os.environ.get("BITUNIX_API_KEY")
        api_secret = os.environ.get("BITUNIX_API_SECRET")
        checks.append(("API_KEY", bool(api_key)))
        checks.append(("API_SECRET", bool(api_secret)))
    else:
        checks.append(("API_KEY (not required)", True))
        checks.append(("API_SECRET (not required)", True))
    
    # 2. Config file
    config_path = Path("config/default.json")
    checks.append(("Config exists", config_path.exists()))
    
    # 3. Logs directory writable
    logs_dir = Path("logs")
    try:
        logs_dir.mkdir(exist_ok=True)
        test_file = logs_dir / ".preflight_test"
        test_file.write_text("test")
        test_file.unlink()
        checks.append(("Logs writable", True))
    except Exception:
        checks.append(("Logs writable", False))
    
    # 4. Network connectivity (Bitunix)
    try:
        import urllib.request
        urllib.request.urlopen("https://fapi.bitunix.com/api/v1/ticker?symbol=BTCUSDT", timeout=5)
        checks.append(("Bitunix connectivity", True))
    except Exception:
        checks.append(("Bitunix connectivity", False))
    
    # 5. Python imports
    try:
        from laptop_agents.session.async_session import run_async_session
        from laptop_agents.paper.broker import PaperBroker
        checks.append(("Core imports", True))
    except Exception:
        checks.append(("Core imports", False))
    
    # Report
    all_passed = all(passed for _, passed in checks)
    
    print("\n======== PREFLIGHT CHECK ========")
    for name, passed in checks:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")
    print("=================================")
    print(f"Result: {'READY' if all_passed else 'NOT READY'}\n")
    
    return all_passed
```

### Verification 9:
```powershell
python -m src.laptop_agents.run --preflight
```

---

## Phase 10: Entry/Exit Timestamps in Trades CSV

**Goal**: Add `entry_ts` and `exit_ts` columns.

### Task 10.1: Update write_trades_csv

**File**: `src/laptop_agents/core/orchestrator.py`

Update `fieldnames`:
```python
fieldnames = ["trade_id", "side", "signal", "entry", "exit", "price", "quantity", "pnl", "fees",
              "entry_ts", "exit_ts", "timestamp", "setup"]
```

### Task 10.2: Populate in journal processing

In the loop that builds trades from journal:
```python
trades.append({
    "trade_id": tid,
    "side": f.get("side", "???"),
    "signal": "MODULAR",
    "entry": float(f.get("price", 0)),
    "exit": float(x.get("price", 0)),
    "quantity": float(f.get("qty", 0)),
    "pnl": float(x.get("pnl", 0)),
    "fees": float(f.get("fees", 0)) + float(x.get("fees", 0)),
    "entry_ts": str(f.get("at", "")),
    "exit_ts": str(x.get("at", "")),
    "timestamp": str(x.get("at", event.get("at", ""))),
    "setup": f.get("setup", "unknown")
})
```

### Verification 10:
```powershell
python -c "from laptop_agents.core.orchestrator import write_trades_csv; print('Import OK')"
```

---

## Phase 11: Zero Volume Warning

**Goal**: Log warning for zero-volume candles.

### Task 11.1: Add volume check

**File**: `src/laptop_agents/session/async_session.py`

In `on_candle_closed`:
```python
if hasattr(candle, 'volume') and float(candle.volume) == 0:
    logger.warning(f"LOW_VOLUME_WARNING: Candle {candle.ts} has zero volume")
```

### Verification 11:
```powershell
python -c "import ast; ast.parse(open('src/laptop_agents/session/async_session.py').read()); print('Syntax OK')"
```

---

## Phase 12: Unit Test for Circuit Breaker

**Goal**: Add test for consecutive loss scenario.

### Task 12.1: Create test file

**File**: `tests/test_circuit_breaker.py` (NEW)

```python
"""Tests for TradingCircuitBreaker."""
import pytest
from laptop_agents.resilience.trading_circuit_breaker import TradingCircuitBreaker

def test_circuit_breaker_trips_on_consecutive_losses():
    cb = TradingCircuitBreaker(max_daily_drawdown_pct=10.0, max_consecutive_losses=5)
    cb.set_starting_equity(10000.0)
    
    # 5 consecutive losses should trip
    for i in range(5):
        cb.update_equity(10000 - (i+1)*100, trade_pnl=-100)
    
    assert cb.is_tripped(), "Circuit breaker should trip after 5 consecutive losses"

def test_circuit_breaker_trips_on_drawdown():
    cb = TradingCircuitBreaker(max_daily_drawdown_pct=5.0, max_consecutive_losses=10)
    cb.set_starting_equity(10000.0)
    
    # 6% drawdown should trip
    cb.update_equity(9400, trade_pnl=-600)
    
    assert cb.is_tripped(), "Circuit breaker should trip on 6% drawdown"

def test_circuit_breaker_resets_on_win():
    cb = TradingCircuitBreaker(max_daily_drawdown_pct=10.0, max_consecutive_losses=5)
    cb.set_starting_equity(10000.0)
    
    # 4 losses then 1 win
    for i in range(4):
        cb.update_equity(10000 - (i+1)*100, trade_pnl=-100)
    cb.update_equity(9800, trade_pnl=200)  # Win resets streak
    
    assert not cb.is_tripped(), "Circuit breaker should not trip after win resets streak"
```

### Verification 12:
```powershell
python -m pytest tests/test_circuit_breaker.py -v --tb=short -p no:cacheprovider
```

---

## Final Verification

Run all checks:

```powershell
# 1. Syntax check all modified files
$env:PYTHONPATH = "src"
python -c "
import ast
files = [
    'src/laptop_agents/session/async_session.py',
    'src/laptop_agents/paper/broker.py',
    'src/laptop_agents/core/orchestrator.py',
    'src/laptop_agents/core/preflight.py',
    'src/laptop_agents/trading/helpers.py',
    'src/laptop_agents/run.py',
]
for f in files:
    ast.parse(open(f).read())
    print(f'OK: {f}')
"

# 2. Run all tests
python -m pytest tests/ -v --tb=short -p no:cacheprovider

# 3. Run preflight check
python -m src.laptop_agents.run --preflight

# 4. Run a 1-minute session
python -m src.laptop_agents.run --mode live-session --duration 1 --source mock --async
```

If all pass, commit with:
```
git add -A
git commit -m "feat(resilience): phase 2 - fsync, error budget, preflight, circuit breaker tests"
```

---

## Commit Message

```
feat(resilience): phase 2 - fsync, error budget, preflight, circuit breaker tests

- Add fsync to append_event for atomic persistence
- Make stale data timeout configurable via --stale-timeout
- Add OrderRejected and TrailActivated events to journal
- Implement error budget with MAX_ERRORS_PER_SESSION
- Add StalePosition warning for long-held positions
- Add candle gap detection utility
- Add broker shutdown timeout (5s)
- Add --preflight system readiness check
- Add entry_ts/exit_ts to trades CSV
- Add zero-volume candle warning
- Add unit tests for circuit breaker scenarios
```
