# CORE RELIABILITY FOUNDATION PLAN

**Priority**: Critical  
**Estimated Scope**: 3 files, ~150 lines modified/added  
**Goal**: Ensure the async trading session can run autonomously for 10 minutes without crashing due to queue overflow, network blips, or state corruption.

---

## EXECUTION PROTOCOL

// turbo-all

1. Read this entire plan before making any changes.
2. Implement each task in order (1.1 → 1.2 → 2.1 → etc.).
3. After each task, run the verification command specified.
4. If verification fails, debug and fix before proceeding.
5. After all tasks complete, run the Final Verification Protocol.
6. Commit all changes with message: `fix(reliability): implement core reliability foundation (queue, WS, state)`

---

## PHASE 1: Non-Blocking Order Execution Queue

### Problem Statement
In `src/laptop_agents/session/async_session.py`, the `on_candle_closed` method uses `await asyncio.sleep(latency / 1000.0)` to simulate execution latency. This blocks the entire event loop, preventing `market_data_task` from consuming WebSocket messages. The internal queue overflows, dropping ticks needed for Stop Loss monitoring.

### Task 1.1: Create Execution Queue Infrastructure
- [x] Create Execution Queue Infrastructure

**File**: `src/laptop_agents/session/async_session.py`

**In `AsyncRunner.__init__`**, add after line ~112 (after `self.shutdown_event = asyncio.Event()`):

```python
# Execution queue for decoupled order processing
self.execution_queue: asyncio.Queue = asyncio.Queue(maxsize=50)
```

**Verification**: 
```powershell
python -c "from laptop_agents.session.async_session import AsyncRunner; r = AsyncRunner('BTCUSDT', '1m'); print('execution_queue exists:', hasattr(r, 'execution_queue'))"
```
Expected output: `execution_queue exists: True`

---

### Task 1.2: Create Execution Task Worker
- [x] Create Execution Task Worker

**File**: `src/laptop_agents/session/async_session.py`

**Add new method** after `async def funding_task(self):` (around line 562):

```python
async def execution_task(self):
    """Consumes orders from execution_queue and processes them with simulated latency."""
    try:
        while not self.shutdown_event.is_set():
            try:
                # Wait for an order with timeout so we can check shutdown
                order_payload = await asyncio.wait_for(
                    self.execution_queue.get(), 
                    timeout=1.0
                )
            except asyncio.TimeoutError:
                continue
            
            order = order_payload.get("order")
            candle = order_payload.get("candle")
            
            if not order or not order.get("go"):
                continue
            
            # Simulate network latency WITHOUT blocking main loop
            if not self.dry_run:
                latency = order_payload.get("latency_ms", 200)
                logger.debug(f"Executing order with {latency}ms simulated latency")
                await asyncio.sleep(latency / 1000.0)
            
            # Get the CURRENT tick after latency (realistic fill price)
            current_tick = self.latest_tick
            
            # Execute via broker
            events = self.broker.on_candle(candle, order, tick=current_tick)
            
            for fill in events.get("fills", []):
                self.trades += 1
                logger.info(f"EXECUTION FILL: {fill['side']} @ {fill['price']}")
                append_event({"event": "ExecutionFill", **fill}, paper=True)
                
            for exit_event in events.get("exits", []):
                self.trades += 1
                logger.info(f"EXECUTION EXIT: {exit_event['reason']} @ {exit_event['price']}")
                append_event({"event": "ExecutionExit", **exit_event}, paper=True)
            
            # Update circuit breaker
            trade_pnl = None
            for exit_event in events.get("exits", []):
                trade_pnl = exit_event.get("pnl", 0)
                
            self.circuit_breaker.update_equity(self.broker.current_equity, trade_pnl)
            
            if self.circuit_breaker.is_tripped():
                logger.warning(f"CIRCUIT BREAKER TRIPPED: {self.circuit_breaker.get_status()}")
                self.shutdown_event.set()
            
            # Save state
            if not self.dry_run:
                self.state_manager.set_circuit_breaker_state(self.circuit_breaker.get_status())
                self.state_manager.save()
                
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Error in execution_task: {e}")
        self.errors += 1
```

**Verification**:
```powershell
python -c "from laptop_agents.session.async_session import AsyncRunner; import inspect; print('execution_task exists:', 'execution_task' in dir(AsyncRunner))"
```
Expected output: `execution_task exists: True`

---

### Task 1.3: Register Execution Task in Run Loop
- [x] Register Execution Task in Run Loop

**File**: `src/laptop_agents/session/async_session.py`

**In `async def run(self, duration_min: int):`**, find the `tasks = [` block (around line 168) and add the execution task:

**FIND**:
```python
        tasks = [
            asyncio.create_task(self.market_data_task()),
            asyncio.create_task(self.watchdog_task()),
            asyncio.create_task(self.heartbeat_task()),
            asyncio.create_task(self.timer_task(end_time)),
            asyncio.create_task(self.kill_switch_task()),
            asyncio.create_task(self.stale_data_task()),
            asyncio.create_task(self.funding_task()),
        ]
```

**REPLACE WITH**:
```python
        tasks = [
            asyncio.create_task(self.market_data_task()),
            asyncio.create_task(self.watchdog_task()),
            asyncio.create_task(self.heartbeat_task()),
            asyncio.create_task(self.timer_task(end_time)),
            asyncio.create_task(self.kill_switch_task()),
            asyncio.create_task(self.stale_data_task()),
            asyncio.create_task(self.funding_task()),
            asyncio.create_task(self.execution_task()),
        ]
```

**Verification**:
```powershell
python -c "import ast; code = open('src/laptop_agents/session/async_session.py').read(); print('execution_task registered:', 'execution_task()' in code)"
```
Expected output: `execution_task registered: True`

---

### Task 1.4: Refactor on_candle_closed to Use Queue
- [x] Refactor on_candle_closed to Use Queue

**File**: `src/laptop_agents/session/async_session.py`

**In `async def on_candle_closed(self, candle: Candle):`**, find and replace the execution block.

**FIND** (approximately lines 415-457, the block starting with `# Execute via broker`):
```python
            # Execute via broker
            current_tick = self.latest_tick
            if order and order.get("go"):
                if not self.dry_run:
                    import random
                    latency = random.randint(50, 500)
                    logger.info(f"Simulating latency: {latency}ms")
                    await asyncio.sleep(latency / 1000.0)
                    # After sleep, we MUST use the newest tick for fill price to avoid look-ahead bias
                    current_tick = self.latest_tick

            events = self.broker.on_candle(candle, order, tick=current_tick)
            
            for fill in events.get("fills", []):
                self.trades += 1
                logger.info(f"STRATEGY FILL: {fill['side']} @ {fill['price']}")
                append_event({"event": "StrategyFill", **fill}, paper=True)
                
            for exit_event in events.get("exits", []):
                self.trades += 1
                logger.info(f"STRATEGY EXIT: {exit_event['reason']} @ {exit_event['price']}")
                append_event({"event": "StrategyExit", **exit_event}, paper=True)

            # Update circuit breaker
            trade_pnl = None
            for exit_event in events.get("exits", []):
                trade_pnl = exit_event.get("pnl", 0)
                
            self.circuit_breaker.update_equity(self.broker.current_equity, trade_pnl)

            if self.circuit_breaker.is_tripped():
                logger.warning(f"CIRCUIT BREAKER TRIPPED: {self.circuit_breaker.get_status()}")
                self.shutdown_event.set()

            # Save state (skip in dry_run for performance/stress-tests)
            if not self.dry_run:
                self.state_manager.set_circuit_breaker_state(self.circuit_breaker.get_status())
                self.state_manager.save()
```

**REPLACE WITH**:
```python
            # Queue order for async execution (non-blocking)
            if order and order.get("go"):
                import random
                latency_ms = random.randint(50, 500)
                logger.info(f"Queuing order for execution (latency: {latency_ms}ms)")
                try:
                    self.execution_queue.put_nowait({
                        "order": order,
                        "candle": candle,
                        "latency_ms": latency_ms,
                        "queued_at": time.time()
                    })
                except asyncio.QueueFull:
                    logger.error("EXECUTION_QUEUE_FULL: Order dropped!")
                    append_event({"event": "OrderDropped", "reason": "queue_full"}, paper=True)
            else:
                # Still process candle for exits on existing positions
                events = self.broker.on_candle(candle, None, tick=self.latest_tick)
                for exit_event in events.get("exits", []):
                    self.trades += 1
                    logger.info(f"CANDLE EXIT: {exit_event['reason']} @ {exit_event['price']}")
                    append_event({"event": "CandleExit", **exit_event}, paper=True)
                    self.circuit_breaker.update_equity(self.broker.current_equity, exit_event.get("pnl", 0))
```

**Verification**:
```powershell
python -c "code = open('src/laptop_agents/session/async_session.py').read(); print('Uses execution_queue:', 'execution_queue.put_nowait' in code); print('No blocking sleep in on_candle_closed:', 'await asyncio.sleep(latency' not in code.split('async def on_candle_closed')[1].split('async def')[0] if 'async def on_candle_closed' in code else False)"
```
Expected: Both `True`

---

## PHASE 2: Harmonize WebSocket Reconnection Policies

### Problem Statement
`AsyncRunner.market_data_task` increments `consecutive_ws_errors` on ANY exception and shuts down after 3. This conflicts with `BitunixWSProvider`'s tenacity-based retry logic, causing premature session termination on recoverable network issues.

### Task 2.1: Reset Error Counter on Success
- [x] Reset Error Counter on Success

**File**: `src/laptop_agents/session/async_session.py`

**In `async def market_data_task(self):`**, find the block that processes items (around line 270):

**FIND**:
```python
                if isinstance(item, Tick):
                    self.latest_tick = item
                    self.last_data_time = time.time()
                    # Immediate watchdog check on EVERY tick is handled by watchdog_task
                    # but we could also trigger it here for even lower latency
```

**REPLACE WITH**:
```python
                if isinstance(item, Tick):
                    self.latest_tick = item
                    self.last_data_time = time.time()
                    # Reset consecutive errors on successful data receipt
                    if self.consecutive_ws_errors > 0:
                        logger.info(f"WS connection recovered. Resetting error count from {self.consecutive_ws_errors} to 0.")
                        self.consecutive_ws_errors = 0
```

**Verification**:
```powershell
python -c "code = open('src/laptop_agents/session/async_session.py').read(); print('Error reset logic exists:', 'consecutive_ws_errors = 0' in code and 'WS connection recovered' in code)"
```
Expected: `True`

---

### Task 2.2: Increase Error Tolerance and Add Backoff
- [x] Increase Error Tolerance and Add Backoff

**File**: `src/laptop_agents/session/async_session.py`

**In `AsyncRunner.__init__`**, find (around line 67-68):
```python
        self.consecutive_ws_errors: int = 0
        self.max_ws_errors: int = 3
```

**REPLACE WITH**:
```python
        self.consecutive_ws_errors: int = 0
        self.max_ws_errors: int = 10  # Increased tolerance; provider has its own tenacity retries
        self.ws_error_backoff_sec: float = 5.0  # Base backoff between reconnect attempts
```

---

### Task 2.3: Implement Exponential Backoff in Error Handler
- [x] Implement Exponential Backoff in Error Handler

**File**: `src/laptop_agents/session/async_session.py`

**In `async def market_data_task(self):`**, find the exception handler (around line 308-314):

**FIND**:
```python
        except Exception as e:
            logger.error(f"Error in market_data_task: {e}")
            self.consecutive_ws_errors += 1
            self.errors += 1
            if self.consecutive_ws_errors >= self.max_ws_errors:
                logger.error(f"WS_FATAL: {self.max_ws_errors} consecutive errors. Triggering shutdown.")
                self.shutdown_event.set()
```

**REPLACE WITH**:
```python
        except asyncio.CancelledError:
            raise  # Don't count cancellation as an error
        except Exception as e:
            logger.error(f"Error in market_data_task: {e}")
            self.consecutive_ws_errors += 1
            self.errors += 1
            
            if self.consecutive_ws_errors >= self.max_ws_errors:
                logger.error(f"WS_FATAL: {self.max_ws_errors} consecutive errors. Triggering shutdown.")
                self.shutdown_event.set()
            else:
                # Exponential backoff before next reconnect attempt
                backoff = min(self.ws_error_backoff_sec * (2 ** (self.consecutive_ws_errors - 1)), 60.0)
                logger.warning(f"WS error #{self.consecutive_ws_errors}. Backing off {backoff:.1f}s before retry...")
                await asyncio.sleep(backoff)
                # Recursively restart the task if not shutdown
                if not self.shutdown_event.is_set():
                    await self.market_data_task()
```

**Verification**:
```powershell
python -c "code = open('src/laptop_agents/session/async_session.py').read(); print('Backoff implemented:', 'ws_error_backoff_sec' in code and 'Exponential backoff' in code or 'Backing off' in code)"
```
Expected: `True`

---

## PHASE 3: Atomic State Persistence with Rotate-Backup

### Problem Statement
`PaperBroker._save_state` writes directly to `state.json`. A crash during write corrupts the file, breaking restart recovery.

### Task 3.1: Implement Backup-Rotate Save Pattern
- [x] Implement Backup-Rotate Save Pattern

**File**: `src/laptop_agents/paper/broker.py`

**FIND the entire `_save_state` method** (around lines 416-445):

```python
    def _save_state(self) -> None:
        if not self.state_path:
            return
        state = {
            "symbol": self.symbol,
            "starting_equity": self.starting_equity,
            "current_equity": self.current_equity,
            "processed_order_ids": list(self.processed_order_ids),
            "order_history": self.order_history,
            "working_orders": self.working_orders,
            "pos": None
        }
        if self.pos:
            state["pos"] = {
                "side": self.pos.side,
                "entry": self.pos.entry,
                "qty": self.pos.qty,
                "sl": self.pos.sl,
                "tp": self.pos.tp,
                "opened_at": self.pos.opened_at,
                "entry_fees": self.pos.entry_fees,
                "bars_open": self.pos.bars_open,
                "trail_active": self.pos.trail_active,
                "trail_stop": self.pos.trail_stop
            }
        
        temp_path = Path(self.state_path).with_suffix(".tmp")
        with open(temp_path, "w") as f:
            json.dump(state, f, indent=2)
        temp_path.replace(self.state_path)
```

**REPLACE WITH**:

```python
    def _save_state(self) -> None:
        if not self.state_path:
            return
        state = {
            "symbol": self.symbol,
            "starting_equity": self.starting_equity,
            "current_equity": self.current_equity,
            "processed_order_ids": list(self.processed_order_ids),
            "order_history": self.order_history,
            "working_orders": self.working_orders,
            "pos": None,
            "saved_at": time.time()  # For debugging
        }
        if self.pos:
            state["pos"] = {
                "side": self.pos.side,
                "entry": self.pos.entry,
                "qty": self.pos.qty,
                "sl": self.pos.sl,
                "tp": self.pos.tp,
                "opened_at": self.pos.opened_at,
                "entry_fees": self.pos.entry_fees,
                "bars_open": self.pos.bars_open,
                "trail_active": self.pos.trail_active,
                "trail_stop": self.pos.trail_stop
            }
        
        main_path = Path(self.state_path)
        temp_path = main_path.with_suffix(".tmp")
        backup_path = main_path.with_suffix(".bak")
        
        try:
            # Step 1: Write to temp file
            with open(temp_path, "w") as f:
                json.dump(state, f, indent=2)
            
            # Step 2: Validate temp file is valid JSON
            with open(temp_path, "r") as f:
                json.load(f)  # Will raise if corrupt
            
            # Step 3: Backup existing state (if exists and valid)
            if main_path.exists():
                try:
                    with open(main_path, "r") as f:
                        json.load(f)  # Validate before backing up
                    import shutil
                    shutil.copy2(main_path, backup_path)
                except (json.JSONDecodeError, Exception):
                    pass  # Don't backup corrupt files
            
            # Step 4: Atomic rename temp -> main
            temp_path.replace(main_path)
            
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            # Clean up temp file if it exists
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
```

**Verification**:
```powershell
python -c "code = open('src/laptop_agents/paper/broker.py').read(); print('Backup pattern:', '.bak' in code and 'shutil.copy2' in code and 'saved_at' in code)"
```
Expected: `True`

---

### Task 3.2: Implement Backup Load Fallback
- [x] Implement Backup Load Fallback

**File**: `src/laptop_agents/paper/broker.py`

**FIND the `_load_state` method** (around lines 447-487) and **REPLACE the entire method**:

```python
    def _load_state(self) -> None:
        path = Path(self.state_path)
        backup_path = path.with_suffix(".bak")
        
        # Try main file first, then backup
        for try_path, is_backup in [(path, False), (backup_path, True)]:
            if not try_path.exists():
                continue
                
            try:
                with open(try_path) as f:
                    state = json.load(f)
                
                self.starting_equity = state.get("starting_equity", self.starting_equity)
                self.current_equity = state.get("current_equity", self.current_equity)
                self.processed_order_ids = set(state.get("processed_order_ids", []))
                self.order_history = state.get("order_history", [])
                self.working_orders = state.get("working_orders", [])
                
                # Expire stale working orders (> 24 hours old)
                now = time.time()
                original_count = len(self.working_orders)
                self.working_orders = [
                    o for o in self.working_orders 
                    if now - o.get("created_at", now) < 86400  # 24 hours
                ]
                if original_count != len(self.working_orders):
                    logger.info(f"Expired {original_count - len(self.working_orders)} stale working orders")
                
                pos_data = state.get("pos")
                if pos_data:
                    self.pos = Position(**pos_data)
                
                source = "backup" if is_backup else "primary"
                logger.info(f"Loaded broker state from {source}: {try_path}")
                
                # If we loaded from backup, immediately save to restore primary
                if is_backup:
                    logger.warning("Loaded from BACKUP. Primary was corrupt. Restoring primary file...")
                    self._save_state()
                
                return  # Success - exit the loop
                
            except json.JSONDecodeError as e:
                logger.error(f"State file corrupt ({try_path}): {e}")
                # Rename corrupt file for debugging
                corrupt_path = try_path.with_suffix(f".corrupt.{int(time.time())}")
                try:
                    try_path.rename(corrupt_path)
                    logger.warning(f"Renamed corrupt file to {corrupt_path}")
                except Exception:
                    pass
                continue  # Try next file
                
            except Exception as e:
                logger.error(f"Failed to load broker state from {try_path}: {e}")
                continue
        
        # If we get here, no valid state was found
        logger.warning("No valid state file found. Starting with fresh state.")
```

**Verification**:
```powershell
python -c "code = open('src/laptop_agents/paper/broker.py').read(); print('Backup load fallback:', 'backup_path' in code and 'Loaded from BACKUP' in code and '.corrupt.' in code)"
```
Expected: `True`

---

### Task 3.3: Add shutil import
- [x] Add shutil import

**File**: `src/laptop_agents/paper/broker.py`

**At the top of the file**, ensure `shutil` is imported. Find the imports section (lines 1-15) and add if missing:

After `from pathlib import Path`, add:
```python
import shutil
```

**Verification**:
```powershell
python -c "import ast; tree = ast.parse(open('src/laptop_agents/paper/broker.py').read()); imports = [n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)]; print('shutil imported:', 'shutil' in imports)"
```
Expected: `True`

---

## FINAL VERIFICATION PROTOCOL

Run all of the following commands. ALL must pass.

### 1. Syntax Check
```powershell
python -m py_compile src/laptop_agents/session/async_session.py src/laptop_agents/paper/broker.py
```
Expected: No output (success)

### 2. Import Check
```powershell
python -c "from laptop_agents.session.async_session import AsyncRunner, run_async_session; from laptop_agents.paper.broker import PaperBroker; print('All imports OK')"
```
Expected: `All imports OK`

### 3. Unit Test Suite
```powershell
python -m pytest tests/ -v --tb=short -x
```
Expected: All tests pass

### 4. Dry-Run Smoke Test (30 seconds)
```powershell
python -m laptop_agents.run --mode live-session --duration 1 --dry-run --symbol BTCUSDT
```
Expected: Completes without errors, shows heartbeat logs

### 5. State Persistence Test
```powershell
python -c "
from laptop_agents.paper.broker import PaperBroker
import tempfile, os, json

# Create broker with state
with tempfile.TemporaryDirectory() as td:
    state_path = os.path.join(td, 'test_state.json')
    b = PaperBroker('BTCUSDT', state_path=state_path)
    b.current_equity = 12345.67
    b._save_state()
    
    # Verify backup exists after second save
    b._save_state()
    backup_exists = os.path.exists(state_path.replace('.json', '.bak'))
    
    # Corrupt primary and verify backup recovery
    with open(state_path, 'w') as f:
        f.write('CORRUPT{{{')
    
    b2 = PaperBroker('BTCUSDT', state_path=state_path)
    recovered = abs(b2.current_equity - 12345.67) < 0.01
    
    print(f'Backup created: {backup_exists}')
    print(f'Recovery from backup: {recovered}')
"
```
Expected: Both `True`

---

## COMMIT PROTOCOL

After all verifications pass:

```powershell
git add src/laptop_agents/session/async_session.py src/laptop_agents/paper/broker.py
git commit -m "fix(reliability): implement core reliability foundation (queue, WS, state)

- Add non-blocking execution queue to prevent event loop starvation
- Harmonize WS reconnection with exponential backoff
- Implement atomic state persistence with backup-rotate pattern
- Reset WS error counter on successful data receipt
- Increase WS error tolerance to 10 (provider has tenacity retries)
"
git push origin main
```

---

## ROLLBACK PROCEDURE

If something goes wrong after commit:

```powershell
git revert HEAD --no-edit
git push origin main
```

---

## SUCCESS CRITERIA

The implementation is complete when:
1. All 5 verification tests pass
2. A 10-minute live-session completes with 0 errors
3. Simulated network disconnect (unplug ethernet for 5s) does NOT crash the session
4. Killing the process mid-run and restarting recovers state correctly
