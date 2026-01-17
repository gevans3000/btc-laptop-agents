# 10-Minute Autonomous Trading Session: Implementation Plan

## Objective
Enable a fully autonomous 10-minute paper trading session that:
1. Stays connected to the exchange feed without crashing.
2. Prevents duplicate orders and runaway positions.
3. Shuts down gracefully with all orders settled.
4. Produces accurate, realistic PnL results.

---

## Phase Dependency Graph
```
Phase 1 (Foundation) ─┬─> Phase 2 (Safety) ─┬─> Phase 3 (Accuracy) ─> Phase 4 (Polish)
                      │                      │
                      └──────────────────────┘
```
Phases 1 and 2 are **blocking**. Do not proceed to Phase 3 until Phases 1 and 2 pass verification.

---

## Phase 1: Connection Reliability (Foundation)
**Goal:** The data feed must survive network blips and detect stale data.

### 1.1 Harden WebSocket Reconnection
- **File:** `src/laptop_agents/data/providers/bitunix_ws.py`
- **Action:** Verify existing `@retry` decorator on `listen()` uses jittered exponential backoff (already present: `wait_exponential(multiplier=1, min=2, max=60)`).
- **Add:** Log `reconnect_attempt_count` metric. Persist last known order book state in `self.last_known_book` before disconnect.
- **Acceptance:** Simulate disconnect by calling `await self.ws_kline.close()` mid-session; system reconnects within 3 attempts and resumes data flow.

### 1.2 Stale Data Detection via Heartbeat
- **File:** `src/laptop_agents/data/providers/bitunix_ws.py`
- **Action:** Existing `_heartbeat_check` sets `self._running = False` after 30s of no messages. **Reduce to 15s for faster detection.**
- **Add:** On stale detection, inject a `StaleDataEvent` into the queue before closing sockets.
- **Acceptance:** Mock frozen feed; trading pauses within 16s and logs `ORDER_BOOK_STALE`.

### 1.3 Exchange Rate Limiter
- **File:** `src/laptop_agents/core/rate_limiter.py` (or create if missing)
- **Action:** Implement token bucket: 20 req/s sustained, 50 req/s burst. Wrap all REST calls in `bitunix_ws.py` and `bitunix_futures.py`.
- **Acceptance:** Stress test with 100 requests in 5s; no 429 responses; `rate_limiter_wait_seconds` metric exposed.

### Phase 1 Verification
```powershell
# Run unit tests for provider resilience
python -m pytest tests/test_bitunix_ws.py -v -k "reconnect or stale or rate"
```

---

## Phase 2: Order Safety (Blocking)
**Goal:** Prevent duplicate orders, runaway positions, and enable emergency stop.

### 2.1 Idempotent Order Placement (Critical)
- **File:** `src/laptop_agents/paper/broker.py`
- **Current State:** `client_order_id` check exists but uses `set()`. **Upgrade to TTL cache (5s) using `cachetools.TTLCache`.**
- **Action:**
  1. In `submit_order()`, generate `client_order_id = uuid.uuid4().hex` if not provided.
  2. Store in `self._idempotency_cache = TTLCache(maxsize=1000, ttl=5)`.
  3. On duplicate detection, return existing order result instead of re-executing.
- **Acceptance:** Call `submit_order()` with same `client_order_id` 5 times; only 1 order appears in `self.positions`.

### 2.2 Symbol-Level Position Cap
- **File:** `config/risk.yaml` (create if missing)
- **Config:**
  ```yaml
  max_position_per_symbol:
    BTCUSDT: 0.1  # BTC
  ```
- **File:** `src/laptop_agents/paper/broker.py`
- **Action:** Before `submit_order()` executes, check:
  ```python
  current_pos = abs(self.positions.get(symbol, {}).get("qty", 0))
  if current_pos + abs(order_qty) > config.max_position_per_symbol.get(symbol, float('inf')):
      logger.warning(f"POSITION_LIMIT_EXCEEDED: {symbol}")
      return {"status": "rejected", "reason": "position_limit"}
  ```
- **Acceptance:** Set cap to 0.05 BTC; attempt to buy 0.1 BTC; order rejected.

### 2.3 Hard Kill-Switch
- **File:** `src/laptop_agents/session/async_session.py`
- **Action:**
  1. On startup, write PID to `.workspace/agent.pid`.
  2. Register `signal.SIGUSR1` (Unix) or poll `os.getenv('LA_KILL_SWITCH')` every 1s.
  3. On trigger, set `self._kill_switch = True`; main loop exits immediately; `broker.close_all()` is called.
- **Acceptance:** Set `$env:LA_KILL_SWITCH = "TRUE"`; trading stops within 2s; exit code is 99.

### Phase 2 Verification
```powershell
# Run safety tests
python -m pytest tests/test_paper_broker.py -v -k "idempotent or position_cap"
# Manual kill-switch test
$env:LA_KILL_SWITCH = "TRUE"; la run --mode paper --duration 60
```

---

## Phase 3: Accuracy Layer
**Goal:** Make paper trading results match reality.

### 3.1 Realistic Slippage Model
- **File:** `src/laptop_agents/paper/broker.py`
- **Action:** In `_execute_fill()`:
  1. If order is `market`, apply slippage: `fill_price = mid_price * (1 + 0.0003 * side_multiplier)` (30bps).
  2. Log `slippage_bps` per fill.
- **Acceptance:** 100 market orders average > 20bps slippage vs. mid.

### 3.2 Maker/Taker Fee Model
- **File:** `config/exchanges/bitunix.yaml`
- **Config:**
  ```yaml
  fees:
    maker: -0.0002  # Rebate
    taker: 0.0005
  ```
- **File:** `src/laptop_agents/paper/broker.py`
- **Action:** Detect order type: if limit order adds liquidity, apply `maker` fee; else `taker`. Adjust PnL.
- **Acceptance:** 10 limit maker orders show negative fees (rebate).

### 3.3 FIFO Cost Basis for PnL
- **File:** `src/laptop_agents/paper/broker.py`
- **Action:** Replace `avg_entry_price` with FIFO lot queue. On sell, deplete oldest lots first.
- **Acceptance:** Buy 0.1 @ $30k, buy 0.1 @ $31k, sell 0.15 @ $32k; realized PnL = `(32000-30000)*0.1 + (32000-31000)*0.05`.

### Phase 3 Verification
```powershell
python -m pytest tests/test_paper_broker.py -v -k "slippage or fee or fifo"
```

---

## Phase 4: Graceful Lifecycle (Polish)
**Goal:** Clean startup and shutdown.

### 4.1 Graceful Shutdown Handler
- **File:** `src/laptop_agents/session/async_session.py`
- **Action:** In `run()` finally block:
  1. Set `self._shutting_down = True`.
  2. Call `await self.broker.cancel_all_open_orders()`.
  3. Wait up to 5s for pending fills.
  4. Persist final state to `paper/state.json`.
  5. Write summary report to `.workspace/runs/{run_id}/summary.json`.
- **Acceptance:** Start session, place 5 limit orders, run `la stop`; all orders cancelled; final state persisted.

### 4.2 Warmup Period (No-Trade Zone)
- **File:** `config/strategies/*.yaml`
- **Config:** `warmup_bars: 50`
- **File:** `src/laptop_agents/agents/orchestrator.py` (or strategy runner)
- **Action:** Set `trading_enabled = False` until `len(candle_buffer) >= warmup_bars`. Log `WARMUP_COMPLETE`.
- **Acceptance:** First 50 bars log no order attempts; bar 51 generates first signal.

### 4.3 Session Summary Report
- **File:** `src/laptop_agents/reporting/summary.py` (create)
- **Action:** On run completion, generate JSON:
  ```json
  {
    "run_id": "...",
    "duration_s": 600,
    "total_trades": 12,
    "realized_pnl_usd": 3.45,
    "max_drawdown_pct": 0.8,
    "slippage_avg_bps": 25,
    "fees_paid_usd": 0.12
  }
  ```
- **Acceptance:** File exists after run; values match SQLite/state.

### Phase 4 Verification
```powershell
la run --mode paper --duration 60
# After run:
Get-Content .workspace/runs/latest/summary.json | ConvertFrom-Json
```

---

## Final Integration Test
```powershell
# Full 10-minute autonomous run
la run --mode paper --symbol BTCUSDT --duration 600

# Expected outcomes:
# 1. No crashes (check logs/system.jsonl for errors)
# 2. summary.json exists with accurate PnL
# 3. No orphaned open orders in paper/state.json
# 4. Kill-switch test: Set $env:LA_KILL_SWITCH="TRUE" mid-run; exits gracefully
```

---

## Implementation Order (Strict Sequence)
| Step | Item | Depends On | Est. Time |
|------|------|------------|-----------|
| 1 | 2.1 Idempotent Orders | None | 30 min |
| 2 | 2.2 Position Cap | None | 20 min |
| 3 | 2.3 Kill-Switch | None | 30 min |
| 4 | 1.1 Reconnect Hardening | None | 20 min |
| 5 | 1.2 Stale Data Detection | 1.1 | 20 min |
| 6 | 1.3 Rate Limiter | None | 30 min |
| 7 | 4.1 Graceful Shutdown | 2.1, 2.2 | 30 min |
| 8 | 3.1 Slippage Model | None | 20 min |
| 9 | 3.2 Fee Model | None | 20 min |
| 10 | 3.3 FIFO PnL | 3.2 | 30 min |
| 11 | 4.2 Warmup Period | None | 15 min |
| 12 | 4.3 Summary Report | 4.1 | 30 min |

**Total:** ~5 hours of focused implementation.

---

## Notes for Autonomous Agent Execution
- Run `/go` workflow after each phase to verify and commit.
- If any test fails, run `/fix` before proceeding.
- All file paths are relative to `c:\Users\lovel\trading\btc-laptop-agents\`.
- Use `SafeToAutoRun: true` for all read/test commands.
