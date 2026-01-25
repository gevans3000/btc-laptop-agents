# Autonomous Trading System V2 - Implementation Plan

This plan is designed to be executed autonomously by an AI agent to upgrade the `btc-laptop-agents` system. The goal is to achieve a highly reliable, realistic 10-minute autonomous paper trading session.

**Execution Rules:**
1.  **Strict Ordering**: Execute phases in order (1 -> 2 -> 3). Do not skip.
2.  **Atomic Commits**: After completing EACH numbered task (e.g., 1.1, 1.2), commit the changes with a semantic message (e.g., `feat: implement process locking`).
3.  **Self-Correction**: If a verification step fails, fix the issue immediately before proceeding.
4.  **No User Input**: Resolve imports, paths, and dependencies autonomously.

---

## Phase 1: Operational Safety & Stability
**Goal**: Ensure the process runs singly, handles crashes gracefully, and doesn't exhaust system resources.

- [x] **1.1 Single-Instance Locking (PID File)**
*Prevents race conditions from overlapping cron jobs or manual runs.*
- **Target**: `src/laptop_agents/run.py`
- **Action**:
    - Import `atexit` and `os`.
    - Define a `LOCK_FILE` path (`.agent/lockfile.pid`).
    - At the start of `main()`:
        - Check if `LOCK_FILE` exists.
        - If yes: Check if the PID inside is running (using `psutil.pid_exists` if available, or broad try/except). If running, print "Already running" and exit(1).
        - If no/stale: Write current PID to `LOCK_FILE`.
    - Register `atexit.register(lambda: os.remove(LOCK_FILE) if os.path.exists(LOCK_FILE) else None)`.
- **Verification**:
    - Run `python src/laptop_agents/run.py --help` (should work).
    - Create a dummy `.agent/lockfile.pid` with the current shell's PID, run the script again, ensure it denies execution.

- [x] **1.2 Global Unhandled Exception Hook & Alerting**
*Ensures fatal crashes (threads/main loop) trigger alerts.*
- **Target**: `src/laptop_agents/run.py` AND `src/laptop_agents/session/async_session.py`
- **Action**:
    - In `run.py`: Define `def handle_exception(exc_type, exc_value, exc_traceback)`.
    - Inside handler: Log the critical error using `logger.critical()` and call `write_alert()` (from `core.logger`).
    - Assign `sys.excepthook = handle_exception`.
    - In `async_session.py`: In the `finally` block of `run()`, if `self.errors > 0` or exit code is non-zero, explicitly call `write_alert(f"Session failed with {self.errors} errors")`.
- **Verification**: Add a temporary `raise Exception("Test Crash")` in `main`. Run it. Check `logs/alert.txt` exists.

- [x] **1.3 Exchange-Specific Fatal Error Parsing**
*Prevents wasteful retries on permanent errors (e.g., invalid API keys, maintenance).*
- **Target**: `src/laptop_agents/data/providers/bitunix_ws.py`
- **Action**:
    - In `_handle_messages`:
        - Parse `data.get("event") == "error"` or `data.get("code")` (if available).
        - If the error code indicates "Invalid Token", "IP Ban", or "Maintenance", raise a custom `FatalError` (subclass of `Exception`, NOT `ConnectionError`).
    - In `listen` (the tenacity loop):
        - Ensure `@retry` does NOT catch `FatalError`. It should bubble up and crash the app (triggering the alert from 1.2).
- **Verification**: Modify code to simulate an "Invalid Token" error msg from WS. Run provider. Ensure it exits immediately instead of retrying 10 times.

- [x] **1.4 Resource Monitoring (RAM/CPU Watchdog)**
*Prevents OOM kills silently terminating the bot.*
- **Target**: `src/laptop_agents/session/async_session.py`
- **Action**:
    - Import `psutil`.
    - In `heartbeat_task`:
        - Get absolute memory usage: `process = psutil.Process(); mem = process.memory_info().rss / 1024 / 1024` (MB).
        - Log `cpu_percent`.
        - **Logic**: If `mem > 1024` (1GB), log CRITICAL "High Memory" and set `self.shutdown_event.set()`.
        - Add these metrics to the `heartbeat.json` file.
- **Verification**: Run session. Check `logs/heartbeat.json` has `ram_mb` field.

---

## Phase 2: Data Integrity & Synchronization
**Goal**: Ensure input data is accurate, time-aligned, and complete.

- [x] **2.1 NTP/Server Time Synchronization**
*Fixes stale data triggers caused by local clock drift.*
- **Target**: `src/laptop_agents/data/providers/bitunix_ws.py`
- **Action**:
    - Add `self.time_offset = 0`.
    - Update `connect()`: Perform one REST call to `https://fapi.bitunix.com/api/v1/time` (or equivalent).
    - Calculate `offset = server_time - local_time`.
    - In `_handle_messages`, when creating `Candle` or `Tick`, adjust `ts = msg_ts - self.time_offset` if the exchange sends server-side timestamps, OR use the offset when comparing `age = time.time() - tick.ts`. *Decision: Trust exchange timestamp, align local `time.time()` comparisons using the offset.*
- **Verification**: Force `self.time_offset = 120000` (2 mins). Run session. Ensure proper timestamps are logged.

- [x] **2.2 Split WebSocket Channels**
*Prevents ticker floods from blocking candle signals.*
- **Target**: `src/laptop_agents/data/providers/bitunix_ws.py`
- **Action**:
    - Split `self.ws` into `self.ws_kline` and `self.ws_ticker`.
    - `connect()` must open both connections.
    - `listen()` must launch two parallel consume loops: `_handle_kline_messages` and `_handle_ticker_messages`.
    - If either disconnects, restart both (simplest approach for V2).
- **Verification**: Run with `--source bitunix`. Ensure logs show "Connected to Kline WS" and "Connected to Ticker WS".

- [x] **2.3 WS Sequence Gap Detection**
*Detects missing candles due to network drops.*
- **Target**: `src/laptop_agents/data/providers/bitunix_ws.py`
- **Action**:
    - Track `self.last_kline_ts`.
    - In `_handle_kline_messages`:
        - If `new_ts > last_kline_ts + interval_seconds`:
            - Log `WARNING: Gap detected!`.
            - Trigger a discrete REST fetch for missing candles (using `loader.load_bitunix_candles`).
            - Inject missing candles into `self.queue`.
- **Verification**: Hardcode a gap logic test (ignore one candle). Verify the gap warning triggers.

---

## Phase 3: Financial Realism & Simulation
**Goal**: Make the paper broker behave exactly like a real exchange.

- [x] **3.1 Dynamic Strategy Warmup**
*Ensures strategies like SMA-200 have enough data to start immediately.*
- **Target**: `src/laptop_agents/agents/supervisor.py` AND `src/laptop_agents/session/async_session.py`
- **Action**:
    - In `StrategyConfig` or `Supervisor`, add `min_history_bars` property (default 100, read from config `engine` section).
    - In `AsyncRunner.run()` (inside `async_session.py`):
        - Read `strategy_config["engine"]["min_history_bars"]`.
        - Set `load_bitunix_candles(limit=max(100, min_history))` during seeding.
- **Verification**: Set `min_history_bars: 500` in config. Run session. Assert `len(self.candles)` is 500 at start.

- [x] **3.2 Order Book Impact & Depth Simulation**
*Simulates slippage for larger orders.*
- **Target**: `src/laptop_agents/paper/broker.py`
- **Action**:
    - In `_try_fill`:
        - Define `simulated_liquidity = 1,000,000` (USD depth).
        - Calculate `market_impact = (order_notional / simulated_liquidity) * 0.05` (5% impact coefficient).
        - `fill_price = price * (1 + market_impact)` (for BUY) or `(1 - market_impact)` (for SELL).
        - Log the "Impact Penalty" separately from random slippage.
- **Verification**: Place a $10 order and a $100,000 order. The $100k order must have a worse fill price.

- [x] **3.3 Funding Rate Simulation**
*Simulates overnight holding costs.*
- **Target**: `src/laptop_agents/paper/broker.py` AND `src/laptop_agents/session/async_session.py`
- **Action**:
    - `broker.py`: Add `apply_funding(rate)`. Logic: `cost = current_position_size * rate`. Deduct from `current_equity`. Log "Funding Fee".
    - `async_session.py`:
        - Every minute, check if `now` crosses 00:00, 08:00, or 16:00 UTC.
        - If yes, fetch funding rate (mock 0.01% or fetch via REST).
        - Call `broker.apply_funding()`.
- **Verification**: Mock the time to be 07:59:59. Run for 2 minutes. Verify funding fee deduction in logs.
