# Autonomous Trading System: Full-Scale Hardening Plan

**Objective**: autonomously upgrade the `btc-laptop-agents` system to achieving a robust, reliable, and realistic 10-minute autonomous paper trading session using live Bitunix data.

**Rules for the Autonomous Agent**:
1.  **Execute sequentially**: Finish one bundle before moving to the next.
2.  **Verify aggressively**: Run the verification command after *every* step. If it fails, fix it immediately.
3.  **Commit often**: `git add . && git commit -m "feat: <description>"` after every successful verification.
4.  **No human input**: If stuck, analyze logs/errors and try a logical fix.
5.  **SafeToAutoRun**: Always set `SafeToAutoRun: true` for non-destructive commands.

---

## Phase 1: Connection & Data Hardening (The "Lifeline" Bundle)
*Goal: Ensure the system never loses the market data connection and handles network instability gracefully.*

### 1.1 Robust WebSocket Reconnection
- **Task**: Modify `src/laptop_agents/data/providers/bitunix_ws.py`.
- **Detail**:
    - Add a `connected` state flag.
    - Updates `listen()` loop to check this flag before calling `_resubscribe()`.
    - Wrap subscription sends in a `try/except` block with exponential backoff.
    - Ensure `_resubscribe` is only called when the socket makes a *fresh* connection.
- **Verification**:
    - Run `python -m laptop_agents.run async --duration 1`.
    - Manually disconnect internet or kill network adapter briefly (if possible to simulate) OR verify logs show "Re-subscribed" only on actual reconnects.

### 1.2 Stale Data Timeout Tuning
- **Task**: Update `src/laptop_agents/session/async_session.py`.
- **Detail**: Change default `stale_timeout` from `60` to `30` seconds in `AsyncRunner.__init__`.
- **Verification**: `grep "stale_timeout: int = 30" src/laptop_agents/session/async_session.py`

### 1.3 WebSocket Backpressure Protection
- **Task**: Modify `src/laptop_agents/data/providers/bitunix_ws.py`.
- **Detail**: In `_handle_messages`, set `asyncio.Queue(maxsize=500)`. If queue is full, drop the oldest item and log a `QUEUE_OVERFLOW` warning.
- **Verification**: Code review of `bitunix_ws.py` to confirm `maxsize=500` is set.

### 1.4 Gap Detection & Backfill
- **Task**: Update `src/laptop_agents/session/async_session.py`.
- **Detail**: In `market_data_task`, after a reconnection event (detectable by strict timestamp jumps or a flag), assume a gap. Call `provider._fetch_and_inject_gap(last_ts, current_ts)` (ensure this method is exposed/accessible).
- **Verification**: Run a session, pause execution (debugger or heavy sleep), resume, and check logs for "GapBackfillComplete".

---

## Phase 2: Execution Realism (The "Market" Bundle)
*Goal: Make paper trading results indistinguishable from real trading by simulating market friction.*

### 2.1 Order Execution Latency
- **Task**: Update `src/laptop_agents/session/async_session.py`.
- **Detail**: In `on_candle_closed`, replace fixed `execution_latency_ms` with `random.randint(50, 500)`.
- **Verification**: Run session, check logs for "Simulated latency: Xms" where X varies.

### 2.2 Synthesized Bid/Ask Spread
- **Task**: Update `src/laptop_agents/paper/broker.py`.
- **Detail**: In `_try_fill`, if `tick` is `None` (tickless mode), do NOT fill at `candle.close`. Instead, calculate:
    - `buy_price = candle.close * (1 + 0.0005)` (5 bps spread)
    - `sell_price = candle.close * (1 - 0.0005)`
- **Verification**: Run `python -m laptop_agents.run async --dry-run` and check fill prices vs candle close.

### 2.3 Live Funding Rate Integration
- **Task**: Update `src/laptop_agents/session/async_session.py`.
- **Detail**: In `funding_task`, replace hardcoded `0.0001` with `self.provider.funding_rate()`. Ensure `BitunixFuturesProvider` has this method working publicly.
- **Verification**: Logs show "FUNDING APPLIED: Rate <actual_rate>" instead of 0.01%.

### 2.4 Max Position Size Enforcement (Safety)
- **Task**: Update `src/laptop_agents/paper/broker.py`.
- **Detail**: In `_try_fill`, add a check: `if entry_px_est <= 0: return None` to prevent division by zero or bad notional calcs on bad data.
- **Verification**: Code review.

---

## Phase 3: Safety Nets (The "Parachute" Bundle)
*Goal: Prevent catastrophic loss and ensure the process behaves well.*

### 3.1 Circuit Breaker Persistence
- **Task**: Update `src/laptop_agents/core/state_manager.py` and `AsyncRunner` (in `src/laptop_agents/session/async_session.py`).
- **Detail**:
    - `StateManager`: track `tripped` status and `trip_reason`.
    - `AsyncRunner`: On startup, load these fields and immediately block trading if `tripped` was True.
- **Verification**:
    1. Trip breaker artificially in code.
    2. Restart session.
    3. Verify logs say "Circuit breaker was previously TRIPPED. It remains TRIPPED."

### 3.2 Robust Kill Switch
- **Task**: Update `src/laptop_agents/session/async_session.py`.
- **Detail**: Change `self.kill_file` path to `REPO_ROOT / "kill.txt"` (import `REPO_ROOT` from `core.orchestrator`).
- **Verification**: Create `c:\Users\lovel\trading\btc-laptop-agents\kill.txt` during a run. Process must exit immediately.

### 3.3 Graceful SIGINT Handling
- **Task**: Update `src/laptop_agents/session/async_session.py`.
- **Detail**: Wrap `asyncio.run(runner.run(...))` in `try/except KeyboardInterrupt`. In the `except` block, call `runner.broker.close_all()` and `runner.broker.shutdown()`.
- **Verification**: Run session, hit `Ctrl+C`. Verify "Final report written" message appears.

---

## Phase 4: State & Persistence (The "Memory" Bundle)
*Goal: Ensure no data is lost during a crash.*

### 4.1 Atomic State Writes
- **Task**: Update `src/laptop_agents/core/state_manager.py`.
- **Detail**: Ensure `save()` writes to `state.json.tmp` first, then renames to `state.json`. (Use `os.replace` for atomic switch).
- **Verification**: Code review of `state_manager.py`.

### 4.2 Order History Persistence
- **Task**: Update `src/laptop_agents/paper/broker.py`.
- **Detail**: Ensure `self.order_history` is included in `_save_state` and restored in `_load_state`.
- **Verification**: Run session, make trades, restart. Verify `order_history` still contains previous trades.

### 4.3 Clean Up Working Orders
- **Task**: Update `src/laptop_agents/paper/broker.py`.
- **Detail**: In `shutdown()`, iterate `working_orders` and clear them, logging `WorkingOrderCancelled` for each.
- **Verification**: Check logs after shutdown for cancellation events.

---

## Phase 5: Observability (The "Black Box" Bundle)
*Goal: Make the system transparent.*

### 5.1 Structured JSON Logs
- **Task**: Modify `src/laptop_agents/core/logger.py`.
- **Detail**: Add support for `JSON_LOGS=1` env var. If set, format logs as `{"level": "INFO", "ts": "...", "msg": "..."}`.
- **Verification**: `set JSON_LOGS=1` -> run -> check console output is JSON.

### 5.2 Metrics Export to CSV
- **Task**: Update `src/laptop_agents/session/async_session.py`.
- **Detail**: In the shutdown sequence (where `metrics.json` is saved), also write `metrics.csv` using `csv.DictWriter`. PnL, equity, price, latencies.
- **Verification**: `runs/latest/metrics.csv` exists after run.

### 5.3 Idempotent Event Logging
- **Task**: Update `src/laptop_agents/core/orchestrator.py`.
- **Detail**: In `append_event`, keep a `set` of `event_id` (create if missing). If `event_id` exists, return early. Use `hash(json.dumps(obj))` as ID if no explicit ID provided.
- **Verification**: Call `append_event` twice with same dict; verify only one line in `events.jsonl`.

---

## Phase 6: Testing & Validation (The "Certification" Bundle)
*Goal: Prove it works.*

### 6.1 State Recovery Unit Test
- **Task**: Create `tests/test_broker_state_recovery.py`.
- **Detail**:
    - Write a valid state file with open position.
    - Initialize `PaperBroker(state_path=...)`.
    - Assert `broker.pos` is not None.
    - Write corrupt file.
    - Assert broker initiates fresh.
- **Verification**: `pytest tests/test_broker_state_recovery.py`.

### 6.2 Async Integration Test
- **Task**: Create `tests/test_async_integration.py`.
- **Detail**: Subclass `BitunixWSProvider` to yield 10 mock candles then stop. Run `AsyncRunner` with this provider. Assert no errors.
- **Verification**: `pytest tests/test_async_integration.py`.

### 6.3 Dry Run Flag
- **Task**: Update `src/laptop_agents/run.py` (CLI entry point).
- **Detail**: Parse `--dry-run` flag. Pass `dry_run=True` to `run_async_session`.
- **Verification**: Run `python -m laptop_agents.run async --dry-run`. Confirm purely simulated execution.
