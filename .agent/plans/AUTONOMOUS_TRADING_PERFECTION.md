# Autonomous Trading System: Perfection & Expansion Plan

**Objective**: Verify and "perfect" the previous hardening work, then implement the next set of critical reliability and observability features.

**Status**: Phase 1 (Connection) and Phase 4 (Persistence) of the previous plan are largely complete. However, deep verification shows that **Gap Detection** and **Synthesized Spread** logic were likely missed or incomplete.

---

## Phase 1: Perfection (Fixing Missing Items)
*Goal: Ensure the "Lifeline" and "Realism" bundles are actually complete.*

### 1.1 Implement Gap Backfill Logic [x]
- **Issue**: `_fetch_and_inject_gap` exists in the provider but is not called by `AsyncRunner`. If the WS disconnects and reconnects, we might miss candles.
- **Task**:
    1.  Modify `src/laptop_agents/session/async_session.py`: `market_data_task`. [x]
    2.  Track `last_candle_ts`. [x]
    3.  On receiving a new candle, check: `if (new_ts - last_candle_ts) > interval_sec * 1.5:` [x]
    4.  If gap detected: `await self.provider.fetch_and_inject_gap(last_candle_ts, new_ts)` (Ensure provider method is public or accessible). [x]

### 1.2 Synthesize Bid/Ask Spread in Tickless Mode [x]
- **Issue**: Currently `broker.py` falls back to `candle.close` + `slip_bps`. This doesn't simulate the cost of crossing the spread (buying at Ask, selling at Bid).
- **Task**:
    1.  Modify `src/laptop_agents/paper/broker.py`: `_try_fill`. [x]
    2.  If `tick` is `None` (or `entry_type == "market"` without tick): [x]
        - `half_spread_bps = 5.0` (0.05%) [x]
        - `ask = close * (1 + half_spread_bps/10000)` [x]
        - `bid = close * (1 - half_spread_bps/10000)` [x]
        - Fill LONG at `ask`, SHORT at `bid`. [x]

---

## Phase 2: Reliability Layer (The "Shield" Bundle) [x]

### 2.1 Shared Rate Limiter Rest/WS [x]
- **Why**: REST calls during backfill can trigger 429s if not coordinated with WS actions.
- **Task**:
    1.  Create `src/laptop_agents/core/rate_limiter.py`: `class RateLimiter`. [x]
    2.  Integrate into `BitunixFuturesProvider` (both REST and WS-init). [x]

### 2.2 Heartbeat Staleness Watchdog [x]
- **Why**: External scripts monitoring `heartbeat.json` don't know if the process is actually writing it or if it's stale.
- **Task**:
    1.  Update `AsyncRunner.heartbeat_task` to include `last_updated_ts`. [x]
    2.  Create `scripts/monitor_heartbeat.py` that alerts if file age > 5s. [x]

### 2.3 Config Validation on Startup [x]
- **Why**: Runtime KeyErrors are fatal mid-session.
- **Task**:
    1.  Create `src/laptop_agents/core/config_models.py` using `pydantic`. [x]
    2.  Define `StrategyConfig` schema. [x]
    3.  In `AsyncRunner.__init__`, validate `strategy_config` against schema. [x]

---

## Phase 3: Observability Expansion (The "Dashboard" Bundle) [x]

### 3.1 Dashboard Flask App [x]
- **Task**:
    1.  Create `src/laptop_agents/dashboard/app.py`. [x]
    2.  Endpoint `/`: Render HTML template showing `heartbeat.json` data + active orders + recent logs. [x]
    3.  Run in separate thread or process (via `scripts/dashboard_up.ps1` enhancement). [x]

### 3.2 HTML Report Equity Curve [x]
- **Task**:
    1.  Modify `src/laptop_agents/reporting/html_renderer.py`. [x]
    2.  Read `runs/latest/equity.csv`. [x]
    3.  Embed Chart.js line chart in `summary.html`. [x]

---

## Phase 4: Stress Testing [x]

### 4.1 High-Load Stress Test [x]
- **Task**:
    1.  Create `tests/stress/test_high_load.py`. [x]
    2.  feed 10,000 mock candles into `AsyncRunner` at max speed. [x]
    3.  Assert `errors == 0`, Memory < 500MB. [x]
- **Verification**: `pytest tests/stress/test_high_load.py`.

---

## Execution Protocol
1.  **Stop**: Ensure no previous sessions are running.
2.  **Execute**: Apply fixes in order.
3.  **Verify**: Run `verify.ps1` or specific pytest after each task.
4.  **Commit**: `git commit -am "feat: ..."`
5.  **Loop**: Continue until plan complete.
