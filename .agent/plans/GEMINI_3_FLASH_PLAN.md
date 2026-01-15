# Gemini 3 Flash Autonomous Coding Plan

## Objective
Enable a robust, realistic, and fully autonomous 10-minute live-data paper trading session. This plan addresses remaining gaps in data ingestion, execution realism, reliability, and observability.

## Phase 1: Real-Time Data & Foundation
**Goal**: Ensure seamless Bitunix data ingestion with keys for higher limits.

### 1.1 Secure & Authenticated Data Ingestion
- **Why**: Currently `loader.py` initializes `BitunixFuturesProvider` without keys, limiting rate limits.
- **What to change**:
  - Update `src/laptop_agents/data/loader.py`: Inject `BITUNIX_API_KEY`/`SECRET` from env into `BitunixFuturesProvider` if available.
  - Update `src/laptop_agents/data/providers/bitunix_futures.py`: Ensure `_raw_get` (used by `klines`) uses API keys if present (switch to `_get_signed` path or add headers to `_raw_get` if keys exist).
- **Acceptance**: `python src/laptop_agents/run.py --source bitunix --preflight` succeeds and uses authenticated requests verified by logs.

### 1.2 Async by Default
- **Why**: Async engine handles high-throughput market data better than sync polling.
- **What to change**:
  - Update `src/laptop_agents/run.py`: Set `default=True` for `--async` flag or make `run_async_session` the default path for `live-session` mode.
  - Ensure `mvp_start_live.ps1` runs the async session.
- **Acceptance**: `mvp_start_live.ps1` starts an async session without extra flags.

## Phase 2: Reliability & Watchdogs
**Goal**: Detect and recover from process freezes.

### 2.1 Threaded Watchdog
- **Why**: The current `async` watchdog shares the event loop; if the loop freezes, the watchdog freezes.
- **What to change**:
  - Modify `src/laptop_agents/session/async_session.py`: add a separate `threading.Thread` that monitors `last_heartbeat_time`.
  - If `last_heartbeat_time` > 30s, the thread should call `os._exit(1)` to force a hard restart.
- **Acceptance**: Induce a `time.sleep(40)` in the main loop; verify process is killed by watchdog thread.

## Phase 3: Execution Realism
**Goal**: Make paper trading accurately allow for spread, fees, and latency.

### 3.1 Real-Time Spread Simulation
- **Why**: Random slippage is inaccurate.
- **What to change**:
  - Update `BitunixWSProvider` (and `AsyncRunner`) to explicitly track `best_bid` and `best_ask` from `ticker` stream.
  - Pass this live spread to `PaperBroker.on_candle` / `on_tick`.
  - Update `PaperBroker`: Use `ask` for BUY fills and `bid` for SELL fills instead of `close` + random slip.
- **Acceptance**: Log filled price vs market mid-price; difference should match half-spread.

### 3.2 Simulated Network Latency
- **Why**: Instant fills differ from reality.
- **What to change**:
  - Add `execution_latency_ms` to config.
  - In `PaperBroker.on_candle` (or caller), `await asyncio.sleep(latency)` before processing fill.
- **Acceptance**: Trade timestamps in `trades.csv` show delay vs signal time.

### 3.3 Dynamic Fee Schedule
- **Why**: Tiered fees affect long-run PnL.
- **What to change**:
  - Create `src/laptop_agents/execution/fees.py`: model Maker/Taker tiers.
  - Update `PaperBroker` to calculate fees based on order type (Limit=Maker, Market=Taker).
- **Acceptance**: `trades.csv` shows different fee rates for Limit vs Market orders.

## Phase 4: Observability
**Goal**: Real-time visibility without tailing logs.

### 4.1 Lightweight Dashboard (Flask)
- **Why**: immediate status check.
- **What to change**:
  - Create `src/laptop_agents/dashboard/app.py`: Simple Flask/FastAPI showing `heartbeat.json` contents.
  - Launch in a separate thread in `run.py` if `--dashboard` flag is set.
- **Acceptance**: Access `http://localhost:5000` to see live Equity/Pos/Price.

### 4.2 Metrics Export
- **Why**: Analysis of system performance.
- **What to change**:
  - In `AsyncRunner`, collect periodic stats (cpu, latency, equity) into a list.
  - Write to `runs/latest/metrics.json` on shutdown.
- **Acceptance**: JSON file contains time-series of system health.

## Phase 5: Testing Harness
**Goal**: Verify robustness before deployment.

### 5.1 Stress Test Script
- **Why**: Ensure 10-min stability under load.
- **What to change**:
  - Create `tests/stress/test_long_run.py`: Mocks WS data at 100x speed.
  - Verifies memory usage doesn't grow linearly.
- **Acceptance**: Pass stress test with < 200MB growth.

## Phase 6: Alerts
**Goal**: Notify on critical failures.

### 6.1 Webhook Alerts
- **Why**: Unattended operation safety.
- **What to change**:
  - Implement `write_alert` to POST to a generic webhook (e.g., Slack/Discord) if `WEBHOOK_URL` is in env.
- **Acceptance**: Trigger fatal error; verify webhook received payload.

## Status
- [x] Phase 1: Real-Time Data & Foundation
- [x] Phase 2: Reliability & Watchdogs
- [x] Phase 3: Execution Realism
- [x] Phase 4: Observability
- [x] Phase 5: Testing Harness
- [x] Phase 6: Alerts

**Plan Status**: COMPLETED
