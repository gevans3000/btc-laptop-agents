# Reliability Hardening Plan: 10-Minute Autonomous Paper Trading

**Objective**: Implement 15 surgical fixes to ensure the paper-trading application runs autonomously for 10 continuous minutes without crashing, hanging, or placing invalid trades.

**Execution Mode**: Fully autonomous. Implement all items in order. No user interaction required.

**Verification**: After all changes, run `python -m pytest tests/ -x -q` and confirm zero failures.

---

## Pre-Implementation Setup

```powershell
# // turbo
cd c:\Users\lovel\trading\btc-laptop-agents
```

---

## Item 1: Timeout-Aware WebSocket Iteration

**File**: `src/laptop_agents/session/async_session.py`
**Location**: `market_data_task()` method, around line 463
**Problem**: `async for item in self.provider.listen()` can block indefinitely if WebSocket yields nothing
**Fix**: Wrap the provider listen iteration with a timeout mechanism

**Implementation**:
```python
# In market_data_task(), replace the direct iteration with timeout-protected version
# Around line 460-465, modify to:

async def market_data_task(self):
    """Consumes WebSocket data and triggers strategy on candle closure."""
    while not self.shutdown_event.is_set():
        try:
            async for item in self.provider.listen():
                if self.shutdown_event.is_set():
                    break
                # Reset timeout timer on each successful item
                self.last_data_time = time.time()
                # ... rest of existing logic
```

**Note**: The existing `stale_data_task` already monitors `last_data_time`. Ensure `last_data_time` is updated immediately when ANY item is received (not just after validation). Move line 496 (`self.last_data_time = time.time()`) to occur right after receiving any item, before validation.

**Acceptance**: No hang >30s when WS produces no data; stale_data_task triggers shutdown.

---

## Item 2: Guard Against NaN/Inf in Candle/Tick Prices

**File**: `src/laptop_agents/session/async_session.py`
**Location**: Lines 484 and 503 in `market_data_task()`
**Problem**: Validation checks `<= 0` but not `math.isnan()` or `math.isinf()`

**Implementation**:
```python
# Add import at top of file (around line 14):
import math

# Modify tick validation (around line 484):
if isinstance(item, Tick):
    # Robust Validation
    if item.last <= 0 or item.ask <= 0 or math.isnan(item.last) or math.isinf(item.last):
        logger.warning("INVALID_TICK: Non-positive or NaN/Inf price. Skipping.")
        continue

# Modify candle validation (around line 503):
elif isinstance(item, Candle):
    # Robust Validation
    if item.close <= 0 or item.open <= 0 or math.isnan(item.close) or math.isinf(item.close):
        logger.warning("INVALID_CANDLE: Non-positive or NaN/Inf price. Skipping.")
        continue
```

**Acceptance**: Zero crashes from NaN/Inf propagation over 10 minutes.

---

## Item 3: Try/Except Around broker.on_tick() in watchdog_tick_task

**File**: `src/laptop_agents/session/async_session.py`
**Location**: `watchdog_tick_task()` method, lines 677-714
**Problem**: If `on_tick` throws, task dies silently, disabling realtime SL/TP

**Implementation**:
```python
# Replace the body of the while loop in watchdog_tick_task (around lines 680-710):
async def watchdog_tick_task(self):
    """Checks open positions against latest tick every 50ms (REALTIME SENTINEL)."""
    try:
        while not self.shutdown_event.is_set():
            if self.latest_tick and self.broker.pos:
                try:
                    events = self.broker.on_tick(self.latest_tick)
                    for exit_event in events.get("exits", []):
                        self.trades += 1
                        logger.info(
                            f"REALTIME_TICK_EXIT: {exit_event['reason']} @ {exit_event['price']}"
                        )
                        # ... rest of exit handling (lines 690-710)
                except Exception as e:
                    logger.error(f"Error in watchdog on_tick: {e}")
                    self.errors += 1

            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        pass
```

**Acceptance**: Task survives exceptions; error count reflects issues.

---

## Item 4: Prevent Double-Shutdown Race

**File**: `src/laptop_agents/session/async_session.py`
**Locations**: Lines 664, 831, 593 (stale_data_task, on_candle_closed, market_data_task)
**Problem**: Multiple tasks increment errors and set shutdown_event, causing race

**Implementation**:
```python
# In stale_data_task (around line 661-670):
if age > self.stale_data_timeout_sec:
    if self.shutdown_event.is_set():
        break  # Already shutting down
    error_msg = f"STALE DATA: No market data for {age:.0f}s. Triggering session restart."
    logger.error(error_msg)
    self.errors += 1
    # ... rest

# In on_candle_closed (around line 831-835):
except Exception as e:
    logger.exception(f"Error in on_candle_closed: {e}")
    self.errors += 1
    if self.errors >= MAX_ERRORS_PER_SESSION and not self.shutdown_event.is_set():
        logger.error(f"ERROR BUDGET EXHAUSTED: {self.errors} errors. Shutting down.")
        self.shutdown_event.set()

# In market_data_task (around line 597-600):
if self.consecutive_ws_errors >= 10:
    if not self.shutdown_event.is_set():
        logger.critical("Too many consecutive WS errors. Giving up.")
        self.shutdown_event.set()
    break
```

**Acceptance**: Exactly one clean shutdown path; no task conflict during termination.

---

## Item 5: Fix Unreachable Except Clause in Gap Detection

**File**: `src/laptop_agents/session/async_session.py`
**Location**: Lines 559-562
**Problem**: Two consecutive except blocks; second is unreachable

**Implementation**:
```python
# Around lines 559-562, REMOVE the duplicate except block:
# BEFORE:
#                         except Exception as ge:
#                             logger.error(f"Error checking for gaps: {ge}")
#                         except (ValueError, TypeError, AttributeError) as ge:
#                             logger.error(f"Error checking for gaps: {ge}")

# AFTER (keep only one):
                        except (ValueError, TypeError, AttributeError, Exception) as ge:
                            logger.error(f"Error checking for gaps: {ge}")
```

**Acceptance**: No unreachable code; gap detection errors logged correctly.

---

## Item 6: Guard funding_task Against Missing funding_rate() Method

**File**: `src/laptop_agents/session/async_session.py`
**Location**: `funding_task()` method, line 977
**Problem**: `BitunixWSProvider` does not implement `funding_rate()`, causing AttributeError

**Implementation**:
```python
# In funding_task(), around line 976-980, add hasattr check:
if (
    now.hour in [0, 8, 16]
    and now.minute == 0
    and now.hour != last_funding_hour
):
    logger.info(f"Funding window detected at {now.hour:02d}:00 UTC")
    if hasattr(self.provider, 'funding_rate') and callable(self.provider.funding_rate):
        try:
            rate = await self.provider.funding_rate()
            logger.info(f"FUNDING APPLIED: Rate {rate:.6f}")
            self.broker.apply_funding(rate, now.isoformat())
        except Exception as fe:
            logger.warning(f"Failed to fetch/apply funding rate: {fe}")
    else:
        logger.debug("Provider does not support funding_rate(). Skipping.")
    last_funding_hour = now.hour
```

**Acceptance**: No crash when funding window fires; logs warning if method absent.

---

## Item 7: Ensure aiohttp.ClientSession Closes on All Exit Paths

**File**: `src/laptop_agents/data/providers/bitunix_ws.py`
**Location**: `_connect_and_stream()` method, lines 86-159
**Problem**: `ctx.close()` only called after loop exits normally; leaks on exception

**Implementation**:
```python
# Replace lines 86-159 with proper async context manager:
async def _connect_and_stream(self):
    async with aiohttp.ClientSession() as ctx:
        while self._running:
            try:
                async with ctx.ws_connect(self.ws_url, heartbeat=30) as ws:
                    logger.info(f"WS: Connected to {self.ws_url} [{self.symbol}]")
                    self.reconnect_delay = 1.0

                    # Subscriptions
                    channels = [
                        f"market.{self.symbol}.kline.1m",
                        f"market.{self.symbol}.ticker",
                    ]
                    for chan in channels:
                        sub_msg = {
                            "event": "sub",
                            "params": {
                                "channel": chan,
                                "cb_id": f"{self.symbol}_{chan}",
                            },
                        }
                        await ws.send_json(sub_msg)

                    async for msg in ws:
                        if not self._running:
                            break

                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            self._last_pong = time.time()
                            if "ping" in data:
                                await ws.send_json({"pong": data["ping"]})
                            elif "event" in data and data["event"] == "channel_pushed":
                                self._handle_push(data)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            logger.error("WS type error")
                            break

                        if not self.is_healthy():
                            logger.warning(
                                "WS: Connection became zombie (no data >20s). Forcefully reconnecting."
                            )
                            break

            except Exception as e:
                if "getaddrinfo failed" in str(e):
                    logger.warning(
                        "WS: Connection failed (DNS/Network Issue). Verify internet connection to Bitunix."
                    )
                else:
                    logger.error(f"WS: Connection error: {e}")

            if self._running:
                wait_s = min(self.reconnect_delay, 60.0)
                jitter = random.uniform(0, 5.0)
                full_wait = wait_s + jitter
                if wait_s >= 8.0 or self.reconnect_delay == 1.0:
                    logger.warning(f"WS: Reconnecting in {full_wait:.1f}s (jittered)...")
                await asyncio.sleep(full_wait)
                self.reconnect_delay *= 2.0
    # Session automatically closed by async with
```

**Acceptance**: Zero leaked HTTP sessions over 10 minutes.

---

## Item 8: Schema Validation for Incoming kline/ticker JSON

**File**: `src/laptop_agents/data/providers/bitunix_ws.py`
**Location**: `_handle_push()` method, lines 165-200
**Problem**: Missing required keys can cause KeyError; bare except masks issues

**Implementation**:
```python
def _handle_push(self, data: Dict[str, Any]):
    try:
        d = data.get("data", {})
        kline = d.get("kline")
        ticker = d.get("ticker")

        if kline:
            # Validate required fields
            required_kline = ["time", "open", "high", "low", "close"]
            if not all(k in kline for k in required_kline):
                logger.warning(f"WS: Malformed kline missing keys: {kline.keys()}")
                return

            c = Candle(
                ts=datetime.fromtimestamp(
                    kline.get("time", 0) / 1000.0, tz=timezone.utc
                ).isoformat(),
                open=float(kline.get("open", 0)),
                high=float(kline.get("high", 0)),
                low=float(kline.get("low", 0)),
                close=float(kline.get("close", 0)),
                volume=float(kline.get("baseVol", 0)),
            )
            with self._lock:
                self._latest_candle = c

        if ticker:
            # Validate required fields
            required_ticker = ["buy", "sell", "last", "time"]
            if not all(k in ticker for k in required_ticker):
                logger.warning(f"WS: Malformed ticker missing keys: {ticker.keys()}")
                return

            t = Tick(
                symbol=self.symbol,
                bid=float(ticker.get("buy", 0)),
                ask=float(ticker.get("sell", 0)),
                last=float(ticker.get("last", 0)),
                ts=datetime.fromtimestamp(
                    ticker.get("time", 0) / 1000.0, tz=timezone.utc
                ).isoformat(),
            )
            with self._lock:
                self._latest_tick = t
    except (KeyError, TypeError, ValueError) as e:
        logger.warning(f"WS: Parse error (malformed data): {e}")
    except Exception as e:
        logger.error(f"WS: Unexpected parse error: {e}")
```

**Acceptance**: Invalid push logs warning and is skipped; no exception bubbling.

---

## Item 9: Prevent Duplicate Order Fills in execution_task

**File**: `src/laptop_agents/session/async_session.py`
**Location**: `execution_task()` method, around line 1001-1005
**Problem**: A queued order could theoretically be processed twice

**Implementation**:
```python
# In execution_task(), after getting order from queue (around line 1001-1005):
order = order_payload.get("order")
candle = order_payload.get("candle")

if not order or not order.get("go"):
    continue

# Add idempotency check:
client_order_id = order.get("client_order_id")
if client_order_id and client_order_id in self.broker.processed_order_ids:
    logger.warning(f"Duplicate order {client_order_id} in execution queue. Skipping.")
    continue
```

**Acceptance**: No duplicate fills logged; processed_order_ids set always checked.

---

## Item 10: Shield broker.shutdown() During Cancellation

**File**: `src/laptop_agents/session/async_session.py`
**Location**: Line 347-351 in `run()` finally block
**Problem**: `broker.shutdown()` can be cancelled by event loop teardown

**Implementation**:
```python
# Around line 347-351, wrap with asyncio.shield:
try:
    await asyncio.wait_for(
        asyncio.shield(asyncio.to_thread(self.broker.shutdown)),
        timeout=5.0
    )
except asyncio.TimeoutError:
    logger.warning("Broker shutdown timed out after 5s")
except Exception as e:
    logger.error(f"Broker shutdown failed: {e}")
```

**Acceptance**: Broker state persisted on every shutdown; no partial state files.

---

## Item 11: Gate on_candle_closed if Candle List Too Short

**File**: `src/laptop_agents/session/async_session.py`
**Location**: `on_candle_closed()` method, around line 716
**Problem**: `self.candles[:-1]` returns empty list if only one candle exists

**Implementation**:
```python
# At the start of on_candle_closed (after line 718):
async def on_candle_closed(self, candle: Candle):
    """Runs strategy logic when a candle is confirmed closed."""
    self.iterations += 1
    logger.info(f"Candle closed: {candle.ts} at {candle.close}")

    # Early exit if insufficient history
    if len(self.candles) < 2:
        logger.debug("Skipping strategy: insufficient candle history (<2)")
        return

    # ... rest of method
```

**Acceptance**: No IndexError or strategy crash with minimal data.

---

## Item 12: Rate-Limit REST Backfill Calls

**File**: `src/laptop_agents/session/async_session.py`
**Location**: `market_data_task()` gap detection, around line 534
**Problem**: Backfill calls can hammer API on reconnect bursts

**Implementation**:
```python
# Add instance variable in __init__ (around line 97):
self._last_backfill_time: float = 0.0

# In market_data_task gap detection (around line 528-558), add rate limit:
if missing_count > 0:
    # Rate limit backfills to max 1 per 30 seconds
    now = time.time()
    if now - self._last_backfill_time < 30.0:
        logger.debug(f"Skipping backfill: rate limited ({now - self._last_backfill_time:.1f}s since last)")
    else:
        logger.warning(
            f"GAP_DETECTED: {missing_count} missing candles. Attempting async backfill..."
        )
        self._last_backfill_time = now
        try:
            fetched = await asyncio.to_thread(
                load_bitunix_candles,
                self.symbol,
                self.interval,
                min(missing_count + 5, 200),
            )
            # ... rest of backfill logic
```

**Acceptance**: No 429 errors logged during 10-minute run.

---

## Item 13: Handle Disk-Full/Permission Errors in StateManager.save()

**File**: `src/laptop_agents/core/state_manager.py`
**Location**: `save()` method, lines 47-73
**Problem**: If log handler also fails on disk full, exception propagates

**Implementation**:
```python
def save(self) -> None:
    """Atomic save via temp file + rename + backup."""
    self._state["last_saved"] = time.time()
    temp = self.state_file.with_suffix(".tmp")
    backup = self.state_file.with_suffix(".bak")

    try:
        with open(temp, "w") as f:
            json.dump(self._state, f, indent=2)
            f.flush()
            import os
            os.fsync(f.fileno())

        # Step 2: Backup current (if exists and valid)
        if self.state_file.exists():
            try:
                import shutil
                shutil.copy2(self.state_file, backup)
            except Exception:
                pass

        # Step 3: Atomic rename
        os.replace(temp, self.state_file)
    except OSError as e:
        # Disk full, permission denied, etc.
        # Use print as logger might also fail
        print(f"CRITICAL: State save failed (disk issue?): {e}")
        try:
            logger.error(f"Failed to save unified state: {e}")
        except Exception:
            pass  # Logger also broken, continue anyway
    except Exception as e:
        try:
            logger.error(f"Failed to save unified state: {e}")
        except Exception:
            print(f"CRITICAL: State save failed: {e}")
```

**Acceptance**: Session continues even if state save fails; alert logged.

---

## Item 14: Initialize _shutting_down Flag in __init__

**File**: `src/laptop_agents/session/async_session.py`
**Location**: `AsyncRunner.__init__()`, around line 97
**Problem**: `self._shutting_down` used at line 308 but never initialized

**Implementation**:
```python
# In __init__, around line 97 (after self.status = "initializing"):
self.status = "initializing"
self._shutting_down = False  # Add this line
```

**Acceptance**: No AttributeError on any code path checking _shutting_down.

---

## Item 15: Structured Logging with Traceback on Exceptions

**File**: `src/laptop_agents/session/async_session.py`
**Locations**: Lines 829, 595, and similar exception handlers
**Problem**: Error logs lack traceback and structured metadata

**Implementation**:
```python
# Line 829 (on_candle_closed exception handler):
except Exception as e:
    logger.exception(f"Error in on_candle_closed: {e}")  # Changed from logger.error
    self.errors += 1
    # ... rest

# Line 595 (market_data_task exception handler):
except Exception as e:
    if self.shutdown_event.is_set():
        break

    self.errors += 1
    self.consecutive_ws_errors += 1
    logger.exception(f"Error in market data stream (attempt {self.consecutive_ws_errors}): {e}")  # Changed from logger.error
    # ... rest

# Line 350-351 (broker shutdown exception):
except Exception as e:
    logger.exception(f"Broker shutdown failed: {e}")  # Changed from logger.error
```

**Acceptance**: Every error in system.jsonl includes timestamp, symbol, and traceback fields.

---

## Post-Implementation Verification

```powershell
# // turbo
cd c:\Users\lovel\trading\btc-laptop-agents

# 1. Format code
python -m black src/laptop_agents/session/async_session.py src/laptop_agents/data/providers/bitunix_ws.py src/laptop_agents/core/state_manager.py

# 2. Lint check
python -m ruff check src/laptop_agents/session/async_session.py src/laptop_agents/data/providers/bitunix_ws.py src/laptop_agents/core/state_manager.py --fix

# 3. Type check
python -m mypy src/laptop_agents/session/async_session.py --ignore-missing-imports

# 4. Run tests
python -m pytest tests/ -x -q

# 5. Quick smoke test (30 second run)
python -m laptop_agents run --mode live-session --duration 1 --source mock --dry-run
```

---

## Commit Message

```
fix(reliability): implement 15 hardening fixes for 10-min autonomous run

- Add timeout-aware WS iteration and NaN/Inf guards
- Wrap watchdog on_tick in try/except
- Fix shutdown race conditions and duplicate except clause
- Guard funding_task against missing provider method
- Ensure aiohttp session cleanup on all exit paths
- Add schema validation for incoming WS data
- Prevent duplicate order fills with idempotency check
- Shield broker.shutdown() during cancellation
- Gate on_candle_closed for minimal candle history
- Rate-limit REST backfill calls to avoid 429
- Handle disk-full errors in StateManager
- Initialize _shutting_down flag
- Use logger.exception for full tracebacks
```

---

## Success Criteria

After implementing all 15 items:
1. `pytest tests/ -x` passes with zero failures
2. `python -m laptop_agents run --mode live-session --duration 10 --source bitunix` completes without crash
3. `logs/system.jsonl` shows zero unhandled exceptions
4. `paper/unified_state.json` is correctly saved on shutdown
