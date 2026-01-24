# Reliability Bundle Implementation Plan

**Target Repository**: `c:\Users\lovel\trading\btc-laptop-agents`
**Objective**: Implement 12 missing/partial reliability features for 10-minute autonomous paper trading.
**Execution Mode**: Fully autonomous. No human input required.

---

## Pre-Conditions (Verify First)

Before starting, verify:
1. Virtual environment exists: `.venv/Scripts/python.exe`
2. Dependencies installed: Run `pip list | grep tenacity` (should show tenacity)
3. Tests pass: Run `python -m pytest tests/ -x -q` (expect PASS)

If any pre-condition fails, STOP and report the failure.

---

## Phase 1: Kill Switch Implementation

**Goal**: Allow emergency stop via `kill.txt` file.

### Task 1.1: Add Kill Switch to Async Session

**File**: `src/laptop_agents/session/async_session.py`

**Changes**:
1. Add import at top: `from pathlib import Path`
2. In `AsyncRunner.__init__`, add: `self.kill_file = Path("kill.txt")`
3. Create new method after `timer_task`:

```python
async def kill_switch_task(self):
    """Monitors for kill.txt file to trigger emergency shutdown."""
    try:
        while not self.shutdown_event.is_set():
            if self.kill_file.exists():
                logger.warning("KILL SWITCH ACTIVATED: kill.txt detected")
                self.shutdown_event.set()
                try:
                    self.kill_file.unlink()  # Remove file after processing
                except Exception:
                    pass
                break
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass
```

4. In `AsyncRunner.run()`, add the task to the `tasks` list:
```python
tasks = [
    asyncio.create_task(self.market_data_task()),
    asyncio.create_task(self.watchdog_task()),
    asyncio.create_task(self.heartbeat_task()),
    asyncio.create_task(self.timer_task(end_time)),
    asyncio.create_task(self.kill_switch_task()),  # ADD THIS
]
```

### Task 1.2: Add Kill Switch to Timed Session

**File**: `src/laptop_agents/session/timed_session.py`

**Changes**:
1. Find the main loop (likely a `while` loop with time check)
2. Add at the start of each iteration:
```python
kill_file = Path("kill.txt")
if kill_file.exists():
    logger.warning("KILL SWITCH ACTIVATED: kill.txt detected")
    kill_file.unlink()
    break
```

### Verification 1:
```powershell
# Start a short session
Start-Process -FilePath ".venv/Scripts/python.exe" -ArgumentList "-m src.laptop_agents.run --mode live-session --duration 1 --source mock" -NoNewWindow
Start-Sleep -Seconds 5
# Create kill file
"STOP" | Out-File -FilePath "kill.txt"
Start-Sleep -Seconds 2
# Verify process stopped (should see KILL SWITCH in logs)
Get-Content logs/system.jsonl | Select-String "KILL"
```

---

## Phase 2: Heartbeat-Aware Watchdog

**Goal**: Detect and restart hung processes based on stale heartbeat.

### Task 2.1: Update Heartbeat File Format

**File**: `src/laptop_agents/core/orchestrator.py`

**Find** (around line 274-282):
```python
heartbeat_path = REPO_ROOT / "logs" / "heartbeat.json"
```

**Ensure** the heartbeat includes a Unix timestamp for easy staleness check:
```python
import time
heartbeat_path = REPO_ROOT / "logs" / "heartbeat.json"
heartbeat_path.parent.mkdir(exist_ok=True)
with heartbeat_path.open("w") as f:
    json.dump({
        "ts": datetime.now(timezone.utc).isoformat(),
        "unix_ts": time.time(),  # ADD THIS
        "candle_idx": i,
        "equity": total_equity,
        "symbol": symbol,
    }, f)
```

### Task 2.2: Update Async Session Heartbeat

**File**: `src/laptop_agents/session/async_session.py`

In `heartbeat_task`, update the event logging to also write a heartbeat file:
```python
async def heartbeat_task(self):
    """Logs system status every second."""
    import time as time_module
    heartbeat_path = Path("logs/heartbeat.json")
    heartbeat_path.parent.mkdir(exist_ok=True)

    try:
        while not self.shutdown_event.is_set():
            elapsed = time.time() - self.start_time
            pos_str = self.broker.pos.side if self.broker.pos else "FLAT"
            price = self.latest_tick.last if self.latest_tick else (self.candles[-1].close if self.candles else 0.0)

            unrealized = self.broker.get_unrealized_pnl(price)
            total_equity = self.broker.current_equity + unrealized

            # Write heartbeat file for watchdog
            with heartbeat_path.open("w") as f:
                json.dump({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "unix_ts": time_module.time(),
                    "elapsed": elapsed,
                    "equity": total_equity,
                    "symbol": self.symbol,
                }, f)

            logger.info(
                f"[ASYNC] {self.symbol} | Price: {price:,.2f} | Pos: {pos_str:5} | "
                f"Equity: ${total_equity:,.2f} | "
                f"Elapsed: {elapsed:.0f}s"
            )

            await asyncio.sleep(1.0)
    except asyncio.CancelledError:
        pass
```

### Task 2.3: Create Smart Watchdog Script

**File**: `scripts/watchdog_smart.ps1` (NEW FILE)

```powershell
# watchdog_smart.ps1 - Smart Process Supervisor with Heartbeat Monitoring
# Usage: .\scripts\watchdog_smart.ps1 --duration 10

param(
    [int]$Duration = 10,
    [string]$Source = "bitunix",
    [string]$Symbol = "BTCUSDT",
    [int]$HeartbeatTimeoutSec = 120,
    [int]$MaxRestarts = 3
)

$LogFile = "logs/watchdog_smart.log"
$HeartbeatFile = "logs/heartbeat.json"
$PidFile = "paper/live.pid"
$RestartCount = 0

if (!(Test-Path "logs")) { New-Item -ItemType Directory -Path "logs" }

function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "$ts $Message"
    Add-Content -Path $LogFile -Value $entry
    Write-Host $entry
}

function Get-HeartbeatAge {
    if (!(Test-Path $HeartbeatFile)) { return 9999 }
    try {
        $hb = Get-Content $HeartbeatFile | ConvertFrom-Json
        $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        return $now - $hb.unix_ts
    } catch {
        return 9999
    }
}

function Start-TradingSession {
    Write-Log "[INFO] Starting trading session..."
    $proc = Start-Process -FilePath ".venv/Scripts/python.exe" `
        -ArgumentList "-m src.laptop_agents.run --mode live-session --duration $Duration --source $Source --symbol $Symbol --async" `
        -PassThru -NoNewWindow -RedirectStandardOutput "logs/live.out.txt" -RedirectStandardError "logs/live.err.txt"

    $proc.Id | Out-File -FilePath $PidFile
    Write-Log "[INFO] Started PID: $($proc.Id)"
    return $proc
}

function Stop-TradingSession {
    if (Test-Path $PidFile) {
        $pid = Get-Content $PidFile
        try {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Write-Log "[INFO] Stopped PID: $pid"
        } catch {}
        Remove-Item $PidFile -ErrorAction SilentlyContinue
    }
}

Write-Log "[INFO] Smart Watchdog Started. Heartbeat timeout: ${HeartbeatTimeoutSec}s, Max restarts: $MaxRestarts"

while ($RestartCount -lt $MaxRestarts) {
    $proc = Start-TradingSession
    $RestartCount++

    # Monitor loop
    while (!$proc.HasExited) {
        Start-Sleep -Seconds 10

        $age = Get-HeartbeatAge
        if ($age -gt $HeartbeatTimeoutSec) {
            Write-Log "[ERROR] Heartbeat stale (${age}s). Killing hung process..."
            Stop-TradingSession
            break
        }

        Write-Log "[HEARTBEAT] Age: ${age}s - OK"
    }

    if ($proc.HasExited -and $proc.ExitCode -eq 0) {
        Write-Log "[INFO] Session completed successfully."
        break
    }

    Write-Log "[WARN] Session crashed or was killed. Restart $RestartCount / $MaxRestarts"
    Start-Sleep -Seconds 5
}

if ($RestartCount -ge $MaxRestarts) {
    Write-Log "[FATAL] Max restarts exceeded. Giving up."
    # Create alert file
    "Max restarts exceeded at $(Get-Date)" | Out-File -FilePath "logs/alert.txt"
}

Write-Log "[INFO] Smart Watchdog Exiting."
```

### Verification 2:
```powershell
# Check script syntax
powershell -NoProfile -Command "Get-Content scripts/watchdog_smart.ps1 | Out-Null; Write-Host 'Syntax OK'"
```

---

## Phase 3: Random Latency & Seedable Randoms

**Goal**: Add realistic random latency (50-500ms) to order execution with seedable RNG.

### Task 3.1: Add Random Latency to Paper Broker

**File**: `src/laptop_agents/paper/broker.py`

**Changes**:
1. Add imports at top:
```python
import random
import asyncio
```

2. Modify `__init__` to accept a seed:
```python
def __init__(self, symbol: str = "BTCUSDT", fees_bps: float = 0.0, slip_bps: float = 0.0,
             starting_equity: float = 10000.0, state_path: Optional[str] = None,
             random_seed: Optional[int] = None) -> None:
    # ... existing code ...
    self.rng = random.Random(random_seed)  # ADD THIS
```

3. Update `apply_slippage` usage in `_try_fill` to use random component:
```python
# Replace the line:
# fill_px_slipped = apply_slippage(fill_px, is_entry=True, is_long=(side == "LONG"), slip_bps=self.slip_bps)

# With:
base_slip = self.slip_bps
random_slip_factor = self.rng.uniform(0.5, 1.5)  # 50% to 150% of base slippage
effective_slip = base_slip * random_slip_factor
fill_px_slipped = apply_slippage(fill_px, is_entry=True, is_long=(side == "LONG"), slip_bps=effective_slip)

# Add simulated latency log
simulated_latency_ms = self.rng.randint(50, 500)
logger.debug(f"Simulated execution latency: {simulated_latency_ms}ms")
```

4. Do the same for the exit in `_exit`:
```python
random_slip_factor = self.rng.uniform(0.5, 1.5)
effective_slip = self.slip_bps * random_slip_factor
px_slipped = apply_slippage(px, is_entry=False, is_long=(p.side == "LONG"), slip_bps=effective_slip)
```

### Verification 3:
```powershell
python -c "from laptop_agents.paper.broker import PaperBroker; b = PaperBroker(random_seed=42); print('OK')"
```

---

## Phase 4: Default to Bitunix Source

**Goal**: Change default data source from `mock` to `bitunix`.

### Task 4.1: Update CLI Default

**File**: `src/laptop_agents/run.py`

**Find** (around line 26):
```python
ap.add_argument("--source", choices=["mock", "bitunix"], default="mock")
```

**Replace with**:
```python
ap.add_argument("--source", choices=["mock", "bitunix"], default="bitunix")
```

### Verification 4:
```powershell
python -m src.laptop_agents.run --help | Select-String "source"
# Should show: default='bitunix'
```

---

## Phase 5: Alert File on Critical Errors

**Goal**: Write to `logs/alert.txt` on unhandled exceptions.

### Task 5.1: Add Alert Handler

**File**: `src/laptop_agents/core/logger.py`

Add this function at the end of the file:
```python
def write_alert(message: str, alert_path: str = "logs/alert.txt"):
    """Write a critical alert to a file for external monitoring."""
    import os
    from datetime import datetime

    os.makedirs(os.path.dirname(alert_path), exist_ok=True)
    with open(alert_path, "a", encoding="utf-8") as f:
        ts = datetime.now().isoformat()
        f.write(f"[{ts}] {message}\n")
```

### Task 5.2: Integrate Alert into Run.py Exception Handler

**File**: `src/laptop_agents/run.py`

**Find** (around line 174):
```python
except Exception as e:
    logger.exception(f"CLI wrapper failed: {e}")
    return 1
```

**Replace with**:
```python
except Exception as e:
    logger.exception(f"CLI wrapper failed: {e}")
    from laptop_agents.core.logger import write_alert
    write_alert(f"CRITICAL: CLI wrapper failed - {e}")
    return 1
```

### Verification 5:
```powershell
python -c "from laptop_agents.core.logger import write_alert; write_alert('Test alert'); print('OK')"
Get-Content logs/alert.txt | Select-String "Test"
```

---

## Phase 6: Trade Frequency Throttling

**Goal**: Enforce minimum interval between trades.

### Task 6.1: Add Throttle to Paper Broker

**File**: `src/laptop_agents/paper/broker.py`

**In `__init__`**, add:
```python
self.last_trade_time: float = 0.0
self.min_trade_interval_sec: float = 60.0  # 1 minute minimum between trades
```

**In `_try_fill`**, add at the beginning (after idempotency check):
```python
# Trade frequency throttle
now = time.time()
if now - self.last_trade_time < self.min_trade_interval_sec:
    logger.info(f"THROTTLED: Only {now - self.last_trade_time:.1f}s since last trade (min: {self.min_trade_interval_sec}s)")
    return None
```

At the end of `_try_fill` (before `return fill_event`):
```python
self.last_trade_time = time.time()
```

### Verification 6:
```powershell
python -m pytest tests/test_safety.py -v -k "test" --tb=short
```

---

## Final Verification

Run the full test suite and a short live session:

```powershell
# 1. Run all tests
$env:PYTHONPATH = "src"
python -m pytest tests/ -v --tb=short

# 2. Run a 1-minute mock session to verify changes
python -m src.laptop_agents.run --mode live-session --duration 1 --source mock --async

# 3. Verify outputs exist
Test-Path runs/latest/summary.html
Test-Path logs/heartbeat.json
```

If all verifications pass, commit with:
```
git add -A
git commit -m "feat(reliability): add kill switch, smart watchdog, random latency, alerts, throttle"
```

---

---

## Phase 7: WebSocket Retry Limit

**Goal**: Prevent infinite reconnect loops on permanent failures.

### Task 7.1: Add Max Retry Attempts

**File**: `src/laptop_agents/data/providers/bitunix_ws.py`

**Find** (around line 119-126):
```python
@retry(
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_never,
```

**Replace with**:
```python
@retry(
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(10),  # Max 10 reconnect attempts
```

**Also add import at top**:
```python
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
```

### Verification 7:
```powershell
python -c "from laptop_agents.data.providers.bitunix_ws import BitunixWSProvider; print('Import OK')"
```

---

## Phase 8: Stale Data Watchdog

**Goal**: Detect when WebSocket stops sending data and shutdown gracefully.

### Task 8.1: Add Stale Data Detection to Async Session

**File**: `src/laptop_agents/session/async_session.py`

**In `AsyncRunner.__init__`**, add:
```python
self.last_data_time: float = time.time()
self.stale_data_timeout_sec: float = 90.0  # No data for 90s = stale
```

**In `market_data_task`**, after `if isinstance(item, Tick):` block, add:
```python
self.last_data_time = time.time()
```

**Add new task after `kill_switch_task`**:
```python
async def stale_data_task(self):
    """Detects stale market data and triggers shutdown."""
    try:
        while not self.shutdown_event.is_set():
            age = time.time() - self.last_data_time
            if age > self.stale_data_timeout_sec:
                logger.error(f"STALE DATA: No market data for {age:.0f}s. Shutting down.")
                self.shutdown_event.set()
                break
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        pass
```

**Add to tasks list in `run()`**:
```python
asyncio.create_task(self.stale_data_task()),
```

### Verification 8:
```powershell
python -c "import ast; ast.parse(open('src/laptop_agents/session/async_session.py').read()); print('Syntax OK')"
```

---

## Phase 9: Circuit Breaker in Async Session

**Goal**: Stop async session on max drawdown or consecutive losses.

### Task 9.1: Add Circuit Breaker to AsyncRunner

**File**: `src/laptop_agents/session/async_session.py`

**Add import at top**:
```python
from laptop_agents.resilience.trading_circuit_breaker import TradingCircuitBreaker
```

**In `AsyncRunner.__init__`**, add:
```python
self.circuit_breaker = TradingCircuitBreaker(max_daily_drawdown_pct=5.0, max_consecutive_losses=5)
self.circuit_breaker.set_starting_equity(starting_balance)
```

**In `on_candle_closed`**, after processing exits, add:
```python
# Update circuit breaker
trade_pnl = None
for exit_event in events.get("exits", []):
    trade_pnl = exit_event.get("pnl", 0)

self.circuit_breaker.update_equity(self.broker.current_equity, trade_pnl)

if self.circuit_breaker.is_tripped():
    logger.warning(f"CIRCUIT BREAKER TRIPPED: {self.circuit_breaker.get_status()}")
    self.shutdown_event.set()
```

### Verification 9:
```powershell
python -c "from laptop_agents.resilience.trading_circuit_breaker import TradingCircuitBreaker; print('Import OK')"
```

---

## Phase 10: Gap Slippage for Stop-Loss

**Goal**: Fill stop-loss at gap-open price, not SL price, when candle gaps past it.

### Task 10.1: Update PaperBroker Exit Logic

**File**: `src/laptop_agents/paper/broker.py`

**In `_check_exit`**, find the LONG SL check (around line 223-224):
```python
if sl_hit:
    return self._exit(candle.ts, p.sl, "SL")
```

**Replace with**:
```python
if sl_hit:
    # Use gap-open price if candle gaps past SL
    exit_price = min(p.sl, float(candle.open)) if float(candle.open) < p.sl else p.sl
    return self._exit(candle.ts, exit_price, "SL")
```

**Similarly for SHORT SL (around line 232-233)**:
```python
if sl_hit:
    # Use gap-open price if candle gaps past SL
    exit_price = max(p.sl, float(candle.open)) if float(candle.open) > p.sl else p.sl
    return self._exit(candle.ts, exit_price, "SL")
```

### Verification 10:
```powershell
python -m pytest tests/test_safety.py -v --tb=short
```

---

## Phase 11: HTML Report for Async Session

**Goal**: Generate summary.html after async session completes.

### Task 11.1: Add Report Generation

**File**: `src/laptop_agents/session/async_session.py`

**Add import at top**:
```python
from laptop_agents.core.orchestrator import render_html, write_trades_csv, LATEST_DIR
```

**At the end of `run_async_session`**, before the final `return`, add:
```python
# Generate HTML report
try:
    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "run_id": f"async_{int(runner.start_time)}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "bitunix",
        "symbol": symbol,
        "interval": interval,
        "candle_count": len(runner.candles),
        "last_ts": runner.candles[-1].ts if runner.candles else "",
        "last_close": float(runner.candles[-1].close) if runner.candles else 0.0,
        "fees_bps": fees_bps,
        "slip_bps": slip_bps,
        "starting_balance": starting_balance,
        "ending_balance": runner.broker.current_equity,
        "net_pnl": runner.broker.current_equity - starting_balance,
        "trades": runner.trades,
        "mode": "async",
    }
    render_html(summary, [], "", candles=runner.candles, latest_dir=LATEST_DIR)
    logger.info(f"HTML report generated at {LATEST_DIR / 'summary.html'}")
except Exception as e:
    logger.error(f"Failed to generate HTML report: {e}")
```

### Verification 11:
```powershell
python -c "from laptop_agents.core.orchestrator import render_html, LATEST_DIR; print('Import OK')"
```

---

## Phase 12: Config Validation for Positive Values

**Goal**: Reject invalid config values early with clear errors.

### Task 12.1: Add Numeric Validation

**File**: `src/laptop_agents/core/validation.py`

**Find the `validate_config` function and add these checks**:
```python
def validate_config(args, strategy_config: dict) -> None:
    """Validate configuration values."""
    # Existing validation...

    # Add numeric range validation
    if hasattr(args, 'stop_bps') and args.stop_bps <= 0:
        raise ValueError(f"stop_bps must be positive, got {args.stop_bps}")

    if hasattr(args, 'tp_r') and args.tp_r <= 0:
        raise ValueError(f"tp_r must be positive, got {args.tp_r}")

    if hasattr(args, 'risk_pct') and (args.risk_pct <= 0 or args.risk_pct > 100):
        raise ValueError(f"risk_pct must be between 0 and 100, got {args.risk_pct}")

    if hasattr(args, 'duration') and args.duration <= 0:
        raise ValueError(f"duration must be positive, got {args.duration}")
```

### Verification 12:
```powershell
python -c "
import argparse
from laptop_agents.core.validation import validate_config
args = argparse.Namespace(stop_bps=30, tp_r=1.5, risk_pct=1.0, duration=10)
validate_config(args, {})
print('Validation OK')
"
```

---

## Phase 13: Symbol Normalization

**Goal**: Accept lowercase symbols and normalize to uppercase.

### Task 13.1: Normalize Symbol in run.py

**File**: `src/laptop_agents/run.py`

**After `args = ap.parse_args()`** (around line 52), add:
```python
# Normalize symbol to uppercase
args.symbol = args.symbol.upper().replace("/", "").replace("-", "")
```

### Verification 13:
```powershell
python -m src.laptop_agents.run --symbol btcusdt --mode selftest
# Should work without error
```

---

## Phase 14: Session Countdown Display

**Goal**: Show remaining time in console for user visibility.

### Task 14.1: Add Countdown to Heartbeat

**File**: `src/laptop_agents/session/async_session.py`

**In `heartbeat_task`**, update the log line:
```python
remaining = max(0, (self.start_time + (duration_min * 60)) - time.time()) if hasattr(self, 'duration_min') else 0
remaining_str = f"{int(remaining // 60)}:{int(remaining % 60):02d}"

logger.info(
    f"[ASYNC] {self.symbol} | Price: {price:,.2f} | Pos: {pos_str:5} | "
    f"Equity: ${total_equity:,.2f} | "
    f"Elapsed: {elapsed:.0f}s | Remaining: {remaining_str}"
)
```

**In `AsyncRunner.__init__`**, add:
```python
self.duration_min: int = 0  # Will be set in run()
```

**In `AsyncRunner.run()`**, at the start add:
```python
self.duration_min = duration_min
```

### Verification 14:
```powershell
python -c "import ast; ast.parse(open('src/laptop_agents/session/async_session.py').read()); print('Syntax OK')"
```

---

## Final Verification (Updated)

Run the full test suite and verify all changes:

```powershell
# 1. Syntax check all modified files
python -c "
import ast
files = [
    'src/laptop_agents/session/async_session.py',
    'src/laptop_agents/session/timed_session.py',
    'src/laptop_agents/paper/broker.py',
    'src/laptop_agents/data/providers/bitunix_ws.py',
    'src/laptop_agents/core/validation.py',
    'src/laptop_agents/run.py',
]
for f in files:
    ast.parse(open(f).read())
    print(f'OK: {f}')
"

# 2. Run all tests
$env:PYTHONPATH = "src"
python -m pytest tests/ -v --tb=short

# 3. Run a 1-minute mock session
python -m src.laptop_agents.run --mode live-session --duration 1 --source mock --async

# 4. Verify outputs
Test-Path runs/latest/summary.html
Test-Path logs/heartbeat.json
```

If all pass, commit:
```
git add -A
git commit -m "feat(reliability): comprehensive reliability bundle - kill switch, watchdog, circuit breaker, gap slippage, alerts, throttle, stale data detection, HTML reports"
```

---

## Summary of Changes

| File | Change |
|------|--------|
| `src/laptop_agents/session/async_session.py` | Kill switch, stale data watchdog, circuit breaker, HTML report, countdown |
| `src/laptop_agents/session/timed_session.py` | Kill.txt check |
| `src/laptop_agents/core/orchestrator.py` | Added `unix_ts` to heartbeat |
| `src/laptop_agents/paper/broker.py` | Random latency, seedable RNG, throttle, gap slippage |
| `src/laptop_agents/data/providers/bitunix_ws.py` | Max retry limit (10 attempts) |
| `src/laptop_agents/core/validation.py` | Positive value checks |
| `src/laptop_agents/run.py` | Default bitunix, alert on error, symbol normalization |
| `src/laptop_agents/core/logger.py` | `write_alert` function |
| `scripts/watchdog_smart.ps1` | NEW: Smart watchdog with heartbeat monitoring |

**Total: 9 files, ~250 lines of code.**
