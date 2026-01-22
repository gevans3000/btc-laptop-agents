# Autonomous 10-Minute Paper Trading Improvements

## Instructions for AI Agent

You are tasked with implementing improvements to a BTC paper-trading application to ensure it can run autonomously for 10 minutes using real market data with high reliability.

### How to Work Through This Document

1. **Work sequentially** - Items are ordered by importance. Complete item 1 before item 2.
2. **For each item**: Read the file, make the change, verify with the acceptance criteria.
3. **Run tests after each change**: `python -m pytest tests/ -x -q`
4. **If a test fails**: Fix the issue before moving to the next item.
5. **Commit after every 5 items** with message: `fix: autonomy improvements batch N`

### Codebase Location
- Root: `c:/Users/lovel/trading/btc-laptop-agents`
- Main source: `src/laptop_agents/`
- Tests: `tests/`

### Key Entry Point
```
la run --mode live-session --duration 10 --source mock --async
```

---

## TIER 1: CRITICAL - Session Will Crash Without These (Items 1-10)

### Item 1: WebSocket Reconnection Backoff Cap and Jitter

**File:** `src/laptop_agents/data/providers/bitunix_ws.py`

**Problem:** Unbounded exponential backoff (doubles forever) and no jitter causes thundering herd after network issues.

**Current Code (lines 115-121):**
```python
if self._running:
    wait_s = min(self.reconnect_delay, 60.0)
    # Only log reconnect attempt every ~minute or so if it keeps failing
    if wait_s >= 8.0 or self.reconnect_delay == 1.0:
        logger.warning(f"WS: Reconnecting in {wait_s}s...")
    await asyncio.sleep(wait_s)
    self.reconnect_delay *= 2.0
```

**Replace With:**
```python
if self._running:
    import random
    # Cap at 30s, add ±20% jitter
    base_wait = min(self.reconnect_delay, 30.0)
    jitter = base_wait * random.uniform(-0.2, 0.2)
    wait_s = max(1.0, base_wait + jitter)
    if wait_s >= 8.0 or self.reconnect_delay == 1.0:
        logger.warning(f"WS: Reconnecting in {wait_s:.1f}s...")
    await asyncio.sleep(wait_s)
    self.reconnect_delay = min(self.reconnect_delay * 2.0, 30.0)
```

**Verify:** Reconnect delay never exceeds 36s (30 + 20% jitter).

---

### Item 2: WebSocket Heartbeat Timeout Detection

**File:** `src/laptop_agents/data/providers/bitunix_ws.py`

**Problem:** `_last_pong` is set but never checked; dead connections hang until stale_data_timeout (60s).

**Current Code (line 31):**
```python
self._last_pong = time.time()
```

**Add after line 100 (inside the `async for msg in ws:` loop, after pong send):**
```python
await ws.send_json({"pong": data["ping"]})
self._last_pong = time.time()  # ADD THIS LINE
```

**Add new check inside the `async for msg in ws:` loop (after processing messages, before end of loop):**
```python
# Check for heartbeat timeout
if time.time() - self._last_pong > 45:
    logger.warning("WS: Heartbeat timeout (no pong in 45s). Forcing reconnect.")
    break
```

**Verify:** If server stops sending pings, reconnect occurs within 45s.

---

### Item 3: Replace Polling with Async Queue in WS Provider

**File:** `src/laptop_agents/data/providers/bitunix_ws.py`

**Problem:** `listen()` polls every 100ms, wasting CPU and adding latency.

**Add to `BitunixWebsocketClient.__init__` (around line 28):**
```python
self._candle_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
```

**Modify `_handle_push` method (around line 125) - add after `self._latest_candle = c`:**
```python
try:
    self._candle_queue.put_nowait(c)
except asyncio.QueueFull:
    pass  # Drop oldest if queue full
```

**Replace entire `BitunixWSProvider.listen` method:**
```python
async def listen(self) -> AsyncGenerator[Union[Candle, Tick, DataEvent], None]:
    self.client.start()
    while True:
        try:
            # Wait for candle from queue with timeout
            c = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, self.client._candle_queue.get
                ),
                timeout=1.0
            )
            if c:
                yield c
        except asyncio.TimeoutError:
            # Yield latest candle as fallback if queue empty
            c = self.client.get_latest_candle()
            if c:
                yield c
        except Exception:
            await asyncio.sleep(0.1)
```

**Verify:** CPU usage drops; latency from WS message to handler <10ms.

---

### Item 4: Unified Timestamp Parsing for Candles

**File:** `src/laptop_agents/trading/helpers.py`

**Problem:** Gap detection expects int timestamps but candles have ISO strings.

**Add new function after line 60:**
```python
def parse_candle_ts(ts: str) -> int:
    """Parse candle timestamp to Unix seconds (int)."""
    if not ts:
        return 0
    # Try int first (Unix timestamp)
    try:
        val = int(ts)
        # If > 10 billion, it's milliseconds
        return val // 1000 if val > 10_000_000_000 else val
    except ValueError:
        pass
    # Try ISO format
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        return int(dt.timestamp())
    except Exception:
        return 0
```

**Update `detect_candle_gaps` function (line 217-220) to use new function:**
```python
for i in range(1, len(candles)):
    prev_ts = parse_candle_ts(candles[i - 1].ts)
    curr_ts = parse_candle_ts(candles[i].ts)
    if prev_ts > 0 and curr_ts > 0:
```

**Update `normalize_candle_order` function (lines 78-85):**
```python
# Parse timestamps for comparison
first_ts = parse_candle_ts(candles[0].ts)
last_ts = parse_candle_ts(candles[-1].ts)

# If first > last, reverse the list
if first_ts > last_ts:
    return list(reversed(candles))
return candles
```

**Verify:** `detect_candle_gaps()` works with both ISO and int timestamps.

---

### Item 5: Seed Failure Should Not Crash Session

**File:** `src/laptop_agents/session/async_session.py`

**Problem:** `FatalError` raised after 5 seed failures crashes the session.

**Replace lines 286-290:**
```python
if len(self.candles) < min_history:
    raise FatalError(
        f"Failed to seed historical candles after 5 attempts "
        f"({len(self.candles)} < {min_history})"
    )
```

**With:**
```python
if len(self.candles) < min_history:
    logger.warning(
        f"SEED_INCOMPLETE: Only {len(self.candles)}/{min_history} candles. "
        f"Proceeding with reduced warmup. Strategy may be less accurate."
    )
    self.errors += 1
    # Don't raise - continue with what we have
    if len(self.candles) == 0:
        # Generate minimal mock candles as last resort
        from laptop_agents.data.loader import load_mock_candles
        self.candles = load_mock_candles(min_history)
        logger.warning(f"FALLBACK: Using {len(self.candles)} mock candles")
```

**Verify:** Block REST endpoint; session starts with mock candles and logs warning.

---

### Item 6: Async Rate Limiter for Seeding

**File:** `src/laptop_agents/core/rate_limiter.py`

**Problem:** `wait_sync()` blocks the event loop during async seeding.

**Add new async method to the rate limiter class:**
```python
async def wait_async(self) -> None:
    """Async version of wait that doesn't block event loop."""
    import asyncio
    while True:
        wait_time = self._get_wait_time()
        if wait_time <= 0:
            self._record_request()
            return
        await asyncio.sleep(wait_time)
```

**File:** `src/laptop_agents/data/loader.py`

**Add new async function after `load_bitunix_candles`:**
```python
async def load_bitunix_candles_async(symbol: str, interval: str, limit: int) -> List[Candle]:
    """Async version that doesn't block event loop."""
    import asyncio
    return await asyncio.to_thread(load_bitunix_candles, symbol, interval, limit)
```

**Verify:** Heartbeat logs continue during seed without stalling.

---

### Item 7: Increase Watchdog Threshold During Seeding

**File:** `src/laptop_agents/session/async_session.py`

**Problem:** 30s watchdog threshold too aggressive during slow REST seeding.

**Add instance variable in `AsyncRunner.__init__` (around line 93):**
```python
self._seeding_complete = False
```

**Set it after seeding completes (after line 298, before "Start tasks"):**
```python
self._seeding_complete = True
```

**Modify `_threaded_watchdog` method (around line 994):**
```python
# Heartbeat check - use longer threshold during seeding
threshold = 30 if self._seeding_complete else 90
age = time.time() - self.last_heartbeat_time
if age > threshold:
```

**Verify:** Slow seed (45s) doesn't trigger watchdog kill.

---

### Item 8: Order Idempotency Cache TTL Increase

**File:** `src/laptop_agents/paper/broker.py`

**Problem:** 5-second TTL too short; retried orders may re-execute.

**Change line 86:**
```python
self._idempotency_cache: TTLCache[str, Any] = TTLCache(maxsize=1000, ttl=5)
```

**To:**
```python
self._idempotency_cache: TTLCache[str, Any] = TTLCache(maxsize=1000, ttl=600)  # 10 minutes
```

**Verify:** Resubmit order after 10s; confirm rejection as duplicate.

---

### Item 9: Handle Execution Queue Full with Backpressure

**File:** `src/laptop_agents/session/async_session.py`

**Problem:** `put_nowait()` drops orders silently when queue full.

**Replace lines 746-759:**
```python
# Queue order for async execution (non-blocking)
if order and order.get("go"):
    latency_ms = random.randint(50, 500)
    logger.info(f"Queuing order for execution (latency: {latency_ms}ms)")
    try:
        self.execution_queue.put_nowait(
            {
                "order": order,
                "candle": candle,
                "latency_ms": latency_ms,
                "queued_at": time.time(),
            }
        )
    except asyncio.QueueFull:
        logger.error("EXECUTION_QUEUE_FULL: Order dropped!")
        append_event(
            {"event": "OrderDropped", "reason": "queue_full"}, paper=True
        )
```

**With:**
```python
# Queue order for async execution with backpressure
if order and order.get("go"):
    latency_ms = random.randint(50, 500)
    logger.info(f"Queuing order for execution (latency: {latency_ms}ms)")
    order_payload = {
        "order": order,
        "candle": candle,
        "latency_ms": latency_ms,
        "queued_at": time.time(),
    }
    try:
        # Try non-blocking first
        self.execution_queue.put_nowait(order_payload)
    except asyncio.QueueFull:
        logger.warning("EXECUTION_QUEUE_FULL: Waiting for space...")
        append_event({"event": "OrderQueueBackpressure"}, paper=True)
        try:
            # Wait up to 5s for space
            await asyncio.wait_for(
                self.execution_queue.put(order_payload),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.error("EXECUTION_QUEUE_TIMEOUT: Order dropped after 5s wait!")
            append_event({"event": "OrderDropped", "reason": "queue_timeout"}, paper=True)
```

**Verify:** Queue full triggers wait, not immediate drop.

---

### Item 10: Graceful Position Closure on SIGTERM

**File:** `src/laptop_agents/session/async_session.py`

**Problem:** Signal handler calls `broker.close_all()` in handler context (unsafe).

**Replace signal handler (lines 1095-1103):**
```python
def handle_sigterm(signum, frame):
    logger.info(f"Signal {signum} received - Forcing broker close.")
    if runner and runner.broker and runner.latest_tick:
        try:
            runner.broker.close_all(runner.latest_tick.last)
        except Exception as e:
            logger.error(f"Failed to close positions on SIGTERM: {e}")
    if runner:
        runner.shutdown_event.set()
```

**With:**
```python
def handle_sigterm(signum, frame):
    logger.info(f"Signal {signum} received - Initiating graceful shutdown.")
    # Only set shutdown event; close_all handled in finally block
    if runner:
        runner._signal_received = True
        runner.shutdown_event.set()
```

**Add instance variable in `AsyncRunner.__init__`:**
```python
self._signal_received = False
```

**In the finally block of `run()` method (around line 341), ensure close_all is called:**
```python
# Final cleanup - close positions if signal received or normal shutdown
if self.broker.pos and self.latest_tick:
    logger.info("Closing open position on shutdown...")
    self.broker.close_all(self.latest_tick.last)
```

**Verify:** SIGTERM during open position; position closes cleanly in events.jsonl.

---

## TIER 2: HIGH PRIORITY - Reliability Improvements (Items 11-25)

### Item 11: Windows SIGBREAK Handler

**File:** `src/laptop_agents/session/async_session.py`

**Problem:** Windows Ctrl+Break not handled.

**Add after line 1113 (inside the Windows signal handling block):**
```python
if hasattr(signal, 'SIGBREAK'):
    signal.signal(signal.SIGBREAK, handle_sigterm)
```

**Verify:** Ctrl+Break triggers graceful shutdown on Windows.

---

### Item 12: Dynamic Slippage Based on Order Size

**File:** `src/laptop_agents/trading/helpers.py`

**Problem:** Static slippage unrealistic for large orders.

**Replace `apply_slippage` function (lines 19-27):**
```python
def apply_slippage(
    price: float, is_entry: bool, is_long: bool, slip_bps: float,
    qty: float = 0.0, typical_volume: float = 1.0
) -> float:
    """Apply slippage, scaling with order size relative to typical volume."""
    base_rate = slip_bps / 10_000.0

    # Scale slippage by order size (larger orders = more slippage)
    if qty > 0 and typical_volume > 0:
        size_factor = 1.0 + (qty / typical_volume) * 0.5  # 50% extra per typical volume
        size_factor = min(size_factor, 3.0)  # Cap at 3x base slippage
    else:
        size_factor = 1.0

    slip_rate = base_rate * size_factor

    if is_long:
        return price * (1.0 + slip_rate) if is_entry else price * (1.0 - slip_rate)
    else:
        return price * (1.0 - slip_rate) if is_entry else price * (1.0 + slip_rate)
```

**Verify:** Large order incurs higher slippage than small order.

---

### Item 13: Funding Rate Call in Thread

**File:** `src/laptop_agents/session/async_session.py`

**Problem:** `funding_rate()` is synchronous, blocks event loop.

**Replace line 910:**
```python
rate = await self.provider.funding_rate()
```

**With:**
```python
try:
    if hasattr(self.provider, 'funding_rate'):
        if asyncio.iscoroutinefunction(self.provider.funding_rate):
            rate = await self.provider.funding_rate()
        else:
            rate = await asyncio.to_thread(self.provider.funding_rate)
    else:
        rate = 0.0001  # Default funding rate
except Exception as e:
    logger.warning(f"Failed to fetch funding rate: {e}. Using default.")
    rate = 0.0001
```

**Verify:** During funding check, heartbeat logs don't stall.

---

### Item 14: Increase MAX_DAILY_LOSS_USD

**File:** `src/laptop_agents/core/hard_limits.py`

**Problem:** $50 on $10k is 0.5%, too low for normal volatility.

**Replace line 7:**
```python
MAX_DAILY_LOSS_USD = 50.0       # Halt if we lose this much in today's runs
```

**With:**
```python
MAX_DAILY_LOSS_USD = float(os.environ.get("LA_MAX_DAILY_LOSS_USD", "500.0"))  # Configurable, default $500
```

**Add at top of file:**
```python
import os
```

**Verify:** 3% drawdown doesn't trigger halt unless configured lower.

---

### Item 15: Fix Preflight Config Path Check

**File:** `src/laptop_agents/core/preflight.py`

**Problem:** Checks `config/default.json` which doesn't exist.

**Replace lines 21-23:**
```python
# 2. Config file
config_path = Path("config/default.json")
checks.append(("Config exists", config_path.exists()))
```

**With:**
```python
# 2. Config files
risk_config = Path("config/risk.yaml")
checks.append(("Risk config exists", risk_config.exists()))
```

**Verify:** Preflight passes with existing config.

---

### Item 16: MockProvider Deterministic Candle Interval

**File:** `src/laptop_agents/data/providers/mock.py`

**Problem:** Candles produced randomly (20% chance), making warmup unpredictable.

**Replace the `listen` method (lines 56-87):**
```python
async def listen(self):
    """Async generator that produces ticks and candles for demo/test."""
    from laptop_agents.trading.helpers import Tick, Candle as IndicatorCandle
    import asyncio
    from laptop_agents.constants import DEFAULT_SYMBOL

    tick_count = 0
    candle_interval = 60  # Produce candle every 60 ticks (simulating 1 tick/sec, 1 candle/min)

    while True:
        tick_count += 1

        # Produce a "Tick"
        self.price = self.price * (1.0 + self.rng.uniform(-0.0002, 0.0002))
        tick = Tick(
            symbol=DEFAULT_SYMBOL,
            bid=self.price * 0.9999,
            ask=self.price * 1.0001,
            last=self.price,
            ts=str(int(datetime.now(timezone.utc).timestamp() * 1000)),
        )
        yield tick

        # Produce candle every candle_interval ticks (deterministic)
        if tick_count % candle_interval == 0:
            c = self.next_candle()
            yield IndicatorCandle(
                ts=c.ts,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
            )

        await asyncio.sleep(0.1)  # 10 ticks/sec = candle every 6 seconds in test mode
```

**Verify:** Warmup completes predictably.

---

### Item 17: Circuit Breaker Daily Reset Fix

**File:** `src/laptop_agents/resilience/trading_circuit_breaker.py`

**Problem:** Date-based reset may trigger mid-session at UTC midnight.

**Replace `set_starting_equity` method (lines 44-56):**
```python
def set_starting_equity(self, equity: float, force_reset: bool = False) -> None:
    """Set the starting equity for the session."""
    # Only reset on explicit request or first call
    if force_reset or self._starting_equity == 0.0:
        self._tripped = False
        self._trip_reason = None
        self._consecutive_losses = 0

    if self._starting_equity == 0.0:
        self._starting_equity = equity
        self._peak_equity = equity
    self._current_equity = equity
```

**Remove the date-based reset logic entirely.**

**Verify:** Session spanning midnight UTC doesn't unexpectedly reset trip status.

---

### Item 18: Agent State Persistence

**File:** `src/laptop_agents/session/async_session.py`

**Problem:** `AgentState` lost on crash; strategy may re-enter same position.

**Add to `checkpoint_task` method (after `self.broker.save_state()` around line 577):**
```python
# Save agent state
if hasattr(self, 'agent_state') and self.agent_state:
    agent_state_dict = {
        "pending_trigger_bars": self.agent_state.pending_trigger_bars,
        "setup": self.agent_state.setup,
        "last_trade_id": getattr(self.agent_state, 'last_trade_id', None),
    }
    self.state_manager.set_supervisor_state(agent_state_dict)
```

**Add to `run` method, after supervisor initialization (around line 188):**
```python
# Restore agent state if available
saved_state = self.state_manager.get_supervisor_state()
if saved_state:
    self.agent_state.pending_trigger_bars = saved_state.get("pending_trigger_bars", 0)
    self.agent_state.setup = saved_state.get("setup", {})
    logger.info(f"Restored agent state: pending_bars={self.agent_state.pending_trigger_bars}")
```

**Verify:** Kill during pending trigger; restart resumes with correct bars count.

---

### Item 19: Duplicate Trade Prevention

**File:** `src/laptop_agents/paper/broker.py`

**Problem:** Crash after fill logged but before state saved may cause duplicate.

**Add to `__init__` (around line 88):**
```python
self.last_trade_id: Optional[str] = None
```

**Add check in `_try_fill` method (around line 152, after idempotency check):**
```python
# Duplicate trade prevention
trade_id = order.get("client_order_id")
if trade_id and trade_id == self.last_trade_id:
    logger.warning(f"Duplicate trade prevention: {trade_id} already executed")
    return None
```

**Set `last_trade_id` after successful fill (before return in `_try_fill`):**
```python
self.last_trade_id = client_order_id
```

**Add to state save/load for persistence.**

**Verify:** Restart with last fill logged; no duplicate trade.

---

### Item 20: Trailing Stop State Persistence Fix

**File:** `src/laptop_agents/paper/broker.py`

**Problem:** `trail_active` and `trail_stop` not in filtered_pos during restore.

**Replace lines 676-681:**
```python
# Clean up keys that Position dataclass doesn't expect
filtered_pos = {
    k: v
    for k, v in pos_data.items()
    if k not in ["entry", "entry_fees"]
}
```

**With:**
```python
# Ensure all Position fields are present with defaults
filtered_pos = {
    "side": pos_data.get("side"),
    "qty": pos_data.get("qty", 0),
    "sl": pos_data.get("sl", 0),
    "tp": pos_data.get("tp", 0),
    "opened_at": pos_data.get("opened_at", ""),
    "lots": pos_data.get("lots", deque()),
    "bars_open": pos_data.get("bars_open", 0),
    "trail_active": pos_data.get("trail_active", False),
    "trail_stop": pos_data.get("trail_stop", 0.0),
}
```

**Verify:** Restart with trailing stop active; stop price preserved.

---

### Item 21: Limit Order History Growth

**File:** `src/laptop_agents/paper/broker.py`

**Problem:** `order_history` grows unbounded.

**Replace line 88:**
```python
self.order_history: List[Dict[str, Any]] = []
```

**With:**
```python
from collections import deque
self.order_history: deque = deque(maxlen=1000)
```

**Update type hints and any list operations accordingly.**

**Verify:** After 1500 trades, history has 1000 entries.

---

### Item 22: Limit Metrics List Growth

**File:** `src/laptop_agents/session/async_session.py`

**Problem:** `metrics` appends every second, growing unbounded.

**Replace line 215:**
```python
self.metrics: List[Dict[str, Any]] = []
```

**With:**
```python
from collections import deque
self.metrics: deque = deque(maxlen=600)  # 10 minutes at 1/sec
```

**Verify:** Memory stable over extended runs.

---

### Item 23: Increase Candle History Window

**File:** `src/laptop_agents/session/async_session.py`

**Problem:** 200 candle cap may truncate strategy lookback.

**Replace lines 546-547:**
```python
# Keep window size
if len(self.candles) > 200:
    self.candles = self.candles[-200:]
```

**With:**
```python
# Keep window size (configurable, default 500)
max_candles = 500
if self.strategy_config:
    max_candles = self.strategy_config.get("engine", {}).get("max_history_bars", 500)
if len(self.candles) > max_candles:
    self.candles = self.candles[-max_candles:]
```

**Verify:** Strategy using 300-period MA has correct calculation.

---

### Item 24: Secret Scrubbing for Shorter Keys

**File:** `src/laptop_agents/core/logger.py`

**Problem:** Regex misses 20-char API keys.

**Replace line 41:**
```python
text = re.sub(r"\b[a-zA-Z0-9]{32,}\b", "***", text)
```

**With:**
```python
text = re.sub(r"\b[a-zA-Z0-9]{16,}\b", "***", text)
```

**Verify:** 20-char key in log appears as `***`.

---

### Item 25: Stale Lock File Cleanup

**File:** `src/laptop_agents/core/lock_manager.py`

**Problem:** Lock file check doesn't verify if PID is alive.

**Add to `acquire` method (or create if doesn't exist):**
```python
import psutil

def acquire(self) -> bool:
    if self.lock_file.exists():
        try:
            pid = int(self.lock_file.read_text().strip())
            if psutil.pid_exists(pid):
                return False  # Process still running
            else:
                # Stale lock, remove it
                logger.info(f"Removing stale lock file (PID {pid} not running)")
                self.lock_file.unlink()
        except (ValueError, OSError):
            # Invalid lock file, remove it
            self.lock_file.unlink()

    # Create new lock
    self.lock_file.parent.mkdir(parents=True, exist_ok=True)
    self.lock_file.write_text(str(os.getpid()))
    return True
```

**Verify:** After crash, new session starts immediately.

---

## TIER 3: MEDIUM PRIORITY - Polish and Edge Cases (Items 26-40)

### Item 26: Signal Confirmation Period

**File:** `src/laptop_agents/trading/signal.py`

**Problem:** No trend confirmation; false crossovers trigger trades.

**Add state tracking (module-level or class):**
```python
_last_signal = None
_signal_bars = 0
CONFIRMATION_BARS = 2
```

**Modify `generate_signal` return logic:**
```python
global _last_signal, _signal_bars

current_signal = "BUY" if fast_sma > slow_sma else "SELL"

if current_signal == _last_signal:
    _signal_bars += 1
else:
    _last_signal = current_signal
    _signal_bars = 1

# Require confirmation
if _signal_bars >= CONFIRMATION_BARS:
    return current_signal
return None
```

**Verify:** Single-bar crossover doesn't trigger trade.

---

### Item 27: Configurable ATR Volatility Threshold

**File:** `src/laptop_agents/trading/signal.py`

**Add parameter to function signature:**
```python
def generate_signal(
    candles: List[Candle],
    fast_period: int = 10,
    slow_period: int = 30,
    volatility_threshold: float = 0.005
) -> Optional[str]:
```

**Replace hardcoded threshold (line 30):**
```python
if volatility_ratio < volatility_threshold:
```

**Verify:** Lower threshold allows more signals.

---

### Item 28: Event Log Rotation

**File:** `src/laptop_agents/core/events.py`

**Problem:** `events.jsonl` can grow unbounded.

**Add rotation logic to `append_event`:**
```python
def _rotate_if_needed(path: Path, max_size_mb: float = 10.0) -> None:
    """Rotate log file if it exceeds max size."""
    if path.exists() and path.stat().st_size > max_size_mb * 1024 * 1024:
        backup = path.with_suffix(f".{int(time.time())}.jsonl")
        path.rename(backup)
        # Keep only last 5 rotated files
        rotated = sorted(path.parent.glob(f"{path.stem}.*.jsonl"))
        for old in rotated[:-5]:
            old.unlink()
```

**Call at start of `append_event`:**
```python
target_dir = PAPER_DIR if paper else LATEST_DIR
target_file = target_dir / "events.jsonl"
_rotate_if_needed(target_file)
```

**Verify:** After 15k events, file rotates.

---

### Item 29: Schema Version in JSON Outputs

**File:** `src/laptop_agents/session/async_session.py`

**Add to all JSON report outputs:**
```python
report = {
    "schema_version": 1,
    "status": "success" if exit_code == 0 else "error",
    # ... rest of fields
}
```

**Do the same for `summary` and `metrics` exports.**

**Verify:** All JSON outputs have `schema_version` field.

---

### Item 30: Klines Paged Fetch Max Pages Guard

**File:** `src/laptop_agents/data/providers/bitunix_futures.py`

**Problem:** Infinite loop possible if API returns future timestamps.

**Add guard in `klines_paged` method (around line 406):**
```python
def klines_paged(
    self, *, interval: str, total: int, end_ms: Optional[int] = None
) -> List[Candle]:
    remaining = int(total)
    cursor_end = end_ms
    all_rows: List[Candle] = []
    max_pages = (total // 200) + 10  # Safety limit
    pages_fetched = 0

    while remaining > 0 and pages_fetched < max_pages:
        pages_fetched += 1
        # ... rest of logic
```

**Verify:** Malformed API doesn't cause infinite loop.

---

### Item 31: Candle Cache for Warm Start

**File:** `src/laptop_agents/session/async_session.py`

**Add at end of `run` method (in finally block):**
```python
# Cache candles for warm start
try:
    cache_path = Path("paper/candle_cache.json")
    cache_path.parent.mkdir(exist_ok=True)
    cache_data = {
        "symbol": self.symbol,
        "interval": self.interval,
        "saved_at": time.time(),
        "candles": [
            {"ts": c.ts, "o": c.open, "h": c.high, "l": c.low, "c": c.close, "v": c.volume}
            for c in self.candles[-200:]
        ]
    }
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)
except Exception:
    pass
```

**Add at start of `run` method (before seeding):**
```python
# Try warm start from cache
try:
    cache_path = Path("paper/candle_cache.json")
    if cache_path.exists():
        with open(cache_path) as f:
            cache = json.load(f)
        if (time.time() - cache.get("saved_at", 0) < 60 and
            cache.get("symbol") == self.symbol):
            self.candles = [
                Candle(ts=c["ts"], open=c["o"], high=c["h"], low=c["l"], close=c["c"], volume=c["v"])
                for c in cache["candles"]
            ]
            logger.info(f"WARM_START: Loaded {len(self.candles)} cached candles")
except Exception:
    pass
```

**Verify:** Restart within 30s; no REST seed needed.

---

### Item 32: Error Circuit Breaker Weighted Errors

**File:** `src/laptop_agents/resilience/error_circuit_breaker.py`

**Add error type weights:**
```python
ERROR_WEIGHTS = {
    "transient": 1,
    "rate_limit": 2,
    "auth": 5,
    "fatal": 5,
}

def record_failure(self, error_type: str = "transient") -> None:
    """Record a failure event with weight based on type."""
    now = time.time()
    weight = self.ERROR_WEIGHTS.get(error_type, 1)
    for _ in range(weight):
        self.failures.append(now)
    self._prune_failures(now)

    if len(self.failures) >= self.failure_threshold:
        self._trip()
```

**Verify:** 5 transient errors don't trip; 1 auth error does.

---

### Item 33: Replay Provider Path Validation

**File:** `src/laptop_agents/session/async_session.py`

**Add validation around line 1080:**
```python
if replay_path:
    replay_file = Path(replay_path)
    if not replay_file.exists():
        raise FileNotFoundError(f"Replay file not found: {replay_path}")
    from laptop_agents.backtest.replay_runner import ReplayProvider
    runner.provider = ReplayProvider(replay_file)
```

**Verify:** Nonexistent path gives clear error before startup.

---

### Item 34: REST Circuit Breaker Tuning

**File:** `src/laptop_agents/data/providers/bitunix_futures.py`

**Replace line 115:**
```python
self.circuit_breaker = CircuitBreaker(max_failures=3, reset_timeout=60)
```

**With:**
```python
self.circuit_breaker = CircuitBreaker(max_failures=5, reset_timeout=30)
```

**Verify:** 4 timeouts don't trip; recovery in 30s.

---

### Item 35: Dashboard Thread Cleanup

**File:** `src/laptop_agents/commands/session.py`

**Store thread reference (around line 156):**
```python
if args.dashboard:
    from laptop_agents.dashboard.app import run_dashboard
    dash_thread = threading.Thread(target=run_dashboard, daemon=True)
    dash_thread.start()
    logger.info("Dashboard launched at http://127.0.0.1:5000")
    atexit.register(lambda: dash_thread.join(timeout=2.0) if dash_thread.is_alive() else None)
```

**Verify:** Dashboard port released after session ends.

---

### Item 36: PositionStore Connection Management

**File:** `src/laptop_agents/storage/position_store.py`

**Replace connection pattern with context manager:**
```python
from contextlib import contextmanager

@contextmanager
def _get_connection(self):
    conn = sqlite3.connect(self.db_path, timeout=10.0)
    try:
        yield conn
    finally:
        conn.close()

def save_state(self, symbol: str, state_data: Dict[str, Any]) -> None:
    try:
        with self._get_connection() as conn:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO state (symbol, data, updated_at) VALUES (?, ?, ?)",
                    (symbol, json.dumps(state_data), time.time()),
                )
    except Exception as e:
        logger.error(f"Failed to save state to DB: {e}")
```

**Verify:** No "database is locked" errors.

---

### Item 37: StateManager Corrupt File Cleanup

**File:** `src/laptop_agents/core/state_manager.py`

**Add cleanup in `_load` method after line 40:**
```python
# Clean up old corrupt files (keep last 5)
corrupt_files = sorted(self.state_dir.glob("*.corrupt.*"))
for old_file in corrupt_files[:-5]:
    try:
        old_file.unlink()
    except Exception:
        pass
```

**Verify:** After 10 corrupt files, only 5 remain.

---

### Item 38: Event Panel Exception Logging

**File:** `src/laptop_agents/core/logger.py`

**Replace lines 185-186:**
```python
except Exception:
    pass
```

**With:**
```python
except Exception as e:
    import logging
    logging.getLogger("btc_agents").debug(f"Event panel render failed: {e}")
```

**Verify:** Malformed event shows debug output.

---

### Item 39: Lot Step Rounding Instead of Truncation

**File:** `src/laptop_agents/agents/supervisor.py`

**Replace line 143:**
```python
qty = int(qty / lot_step) * lot_step
```

**With:**
```python
original_qty = qty
qty = round(qty / lot_step) * lot_step
if abs(original_qty - qty) / original_qty > 0.01:
    from laptop_agents.core.logger import logger
    logger.info(f"Qty adjusted from {original_qty:.6f} to {qty:.6f} for lot step {lot_step}")
```

**Verify:** Qty 0.0047 with lot_step 0.001 becomes 0.005.

---

### Item 40: Risk Gate Margin Calculation

**File:** `src/laptop_agents/agents/risk_gate.py`

**Add margin check in `run` method:**
```python
def run(self, state: State) -> State:
    if not state.order.get("go"):
        return state

    # Check available margin including unrealized PnL
    equity = float(state.order.get("equity", 10000))
    unrealized = 0.0  # Would need broker reference to calculate

    order_notional = float(state.order.get("qty", 0)) * float(state.order.get("entry", 0))
    max_allowed = equity * 0.9  # Reserve 10% margin

    if order_notional > max_allowed:
        state.order = {"go": False, "reason": "insufficient_margin"}

    return state
```

**Verify:** Large unrealized loss blocks new orders.

---

## TIER 4: LOW PRIORITY - Nice to Have (Items 41-50)

### Item 41: Add 10-Minute Session Stress Test

**File:** `tests/stress/test_10min_session.py` (CREATE NEW)

```python
import pytest
import asyncio
from laptop_agents.session.async_session import run_async_session

@pytest.mark.asyncio
@pytest.mark.slow
async def test_10min_mock_session():
    """Full 10-minute session with mock provider."""
    result = await run_async_session(
        duration_min=10,
        symbol="BTCUSDT",
        interval="1m",
        strategy_config={"source": "mock"},
        dry_run=True,
    )

    assert result.errors == 0
    assert result.duration_sec >= 590  # Allow 10s tolerance
    assert result.stopped_reason == "completed"
```

**Run:** `python -m pytest tests/stress/test_10min_session.py -v`

---

### Item 42: Structured Error Codes

**File:** `src/laptop_agents/core/errors.py` (CREATE NEW)

```python
from enum import IntEnum

class ErrorCode(IntEnum):
    SUCCESS = 0
    UNKNOWN = 1
    CIRCUIT_BREAKER_TRIP = 2
    SEED_FAILURE = 3
    STALE_DATA = 4
    KILL_SWITCH = 99

def get_exit_code(result) -> int:
    if result.errors == 0:
        return ErrorCode.SUCCESS
    if result.stopped_reason == "circuit_breaker":
        return ErrorCode.CIRCUIT_BREAKER_TRIP
    if result.stopped_reason == "stale_data":
        return ErrorCode.STALE_DATA
    return ErrorCode.UNKNOWN
```

**Use in session.py exit logic.**

---

### Item 43: Health Endpoint

**File:** `src/laptop_agents/session/async_session.py`

**Add to `run` method after task creation:**
```python
# Optional health endpoint
async def health_handler(request):
    return web.json_response({
        "status": "running",
        "equity": self.broker.current_equity,
        "uptime": time.time() - self.start_time,
        "errors": self.errors,
    })

try:
    from aiohttp import web
    app = web.Application()
    app.router.add_get("/health", health_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8080)
    await site.start()
    logger.info("Health endpoint at http://127.0.0.1:8080/health")
except Exception:
    pass  # Health endpoint optional
```

**Add `aiohttp` to dependencies in pyproject.toml.**

---

### Item 44: Bitunix Live Connectivity Test

**File:** `tests/manual/test_bitunix_connectivity.py` (CREATE NEW)

```python
import pytest
import os

@pytest.mark.skipif(
    not os.environ.get("BITUNIX_API_KEY"),
    reason="No API key configured"
)
def test_bitunix_candles():
    from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider

    provider = BitunixFuturesProvider(symbol="BTCUSDT")
    candles = provider.klines(interval="1m", limit=5)

    assert len(candles) == 5
    assert all(c.close > 0 for c in candles)
```

---

### Item 45: Dry Run Skip File Writes

**File:** `src/laptop_agents/core/events.py`

**Add dry_run parameter:**
```python
_DRY_RUN = False

def set_dry_run(enabled: bool) -> None:
    global _DRY_RUN
    _DRY_RUN = enabled

def append_event(obj: Dict[str, Any], paper: bool = False) -> None:
    # ... existing idempotency logic ...

    if _DRY_RUN:
        return  # Skip file writes in dry run

    # ... rest of function
```

**Call `set_dry_run(True)` in AsyncRunner when `dry_run=True`.**

---

### Item 46: Gap Backfill Implementation

**File:** `src/laptop_agents/data/providers/bitunix_ws.py`

**Add method to BitunixWSProvider:**
```python
async def fetch_and_inject_gap(self, start_ts: int, end_ts: int) -> None:
    """Fetch missing candles via REST and inject into history."""
    from laptop_agents.data.loader import load_bitunix_candles
    import asyncio

    try:
        gap_seconds = end_ts - start_ts
        needed = (gap_seconds // 60) + 1
        candles = await asyncio.to_thread(
            load_bitunix_candles, self.symbol, "1m", min(needed, 200)
        )

        with self.client._lock:
            # Inject into history
            for c in candles:
                ts = int(c.ts) if c.ts.isdigit() else 0
                if start_ts < ts < end_ts:
                    self.client._history.append(c)
            # Sort by timestamp
            self.client._history.sort(key=lambda x: x.ts)

        logger.info(f"Backfilled {len(candles)} candles for gap")
    except Exception as e:
        logger.error(f"Gap backfill failed: {e}")
```

---

### Item 47: Exchange Fee Config Priority

**File:** `src/laptop_agents/paper/broker.py`

**Replace lines 80-84:**
```python
# Override with constructor args if provided to support old tests
if fees_bps != 0:
    self.exchange_fees = {
        "maker": fees_bps / 10000.0,
        "taker": fees_bps / 10000.0,
    }
```

**With:**
```python
# Only override if explicitly passed (use -1 as sentinel for "use config")
if fees_bps > 0:
    self.exchange_fees = {
        "maker": fees_bps / 10000.0,
        "taker": fees_bps / 10000.0,
    }
# fees_bps=0 means use exchange config (already loaded)
```

---

### Item 48: Add Schema Migration to PositionStore

**File:** `src/laptop_agents/storage/position_store.py`

**Add schema version tracking:**
```python
SCHEMA_VERSION = 2

def _init_db(self) -> None:
    # ... existing table creation ...

    # Schema migrations
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_info (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cursor = conn.execute("SELECT value FROM schema_info WHERE key='version'")
    row = cursor.fetchone()
    current_version = int(row[0]) if row else 0

    if current_version < SCHEMA_VERSION:
        self._run_migrations(conn, current_version)
        conn.execute(
            "INSERT OR REPLACE INTO schema_info VALUES (?, ?)",
            ("version", str(SCHEMA_VERSION))
        )

    conn.commit()

def _run_migrations(self, conn, from_version: int) -> None:
    if from_version < 2:
        # Add any new columns needed
        logger.info("Running migration to schema v2")
```

---

### Item 49: Risk Gate with Unrealized PnL

**File:** `src/laptop_agents/agents/risk_gate.py`

**Inject broker reference and calculate properly:**
```python
def __init__(self, cfg: Dict[str, Any], broker: Any = None):
    self.cfg = cfg
    self.broker = broker
    self.max_risk_pct = cfg.get("max_risk_pct", 5.0)

def run(self, state: State) -> State:
    if not state.order.get("go"):
        return state

    equity = float(state.order.get("equity", 10000))

    # Calculate available margin including unrealized
    if self.broker and hasattr(self.broker, 'get_unrealized_pnl'):
        current_price = float(state.order.get("entry", 0))
        unrealized = self.broker.get_unrealized_pnl(current_price)
        available = equity + unrealized
    else:
        available = equity

    # Block if using too much margin
    order_notional = float(state.order.get("qty", 0)) * float(state.order.get("entry", 0))
    if order_notional > available * 0.9:
        state.order = {"go": False, "reason": "margin_exceeded"}

    return state
```

---

### Item 50: Partial Fill Simulation

**File:** `src/laptop_agents/paper/broker.py`

**Add to `_try_fill` method:**
```python
# Simulate partial fills based on typical volume
typical_volume_usd = 100000  # Configurable
order_notional = qty_requested * float(candle.close)

if order_notional > typical_volume_usd:
    # Partial fill - take what's available
    fill_ratio = min(1.0, typical_volume_usd / order_notional)
    actual_qty = qty_requested * fill_ratio

    if fill_ratio < 1.0:
        logger.info(f"PARTIAL_FILL: {fill_ratio:.1%} of requested qty")
        # Queue remainder as working order
        remaining_order = order.copy()
        remaining_order["qty"] = qty_requested - actual_qty
        self.working_orders.append(remaining_order)
else:
    actual_qty = qty_requested
```

---

## Completion Checklist

After implementing all items:

1. [ ] Run full test suite: `python -m pytest tests/ -v`
2. [ ] Run type check: `python -m mypy src/laptop_agents --ignore-missing-imports`
3. [ ] Run 10-minute mock session: `la run --mode live-session --duration 10 --source mock --async`
4. [ ] Verify `final_report.json` shows `"errors": 0`
5. [ ] Verify no crashes in `autonomy_error.log`

## Final Commit
```
git add -A
git commit -m "feat: complete autonomy improvements for 10-minute paper trading"
```
