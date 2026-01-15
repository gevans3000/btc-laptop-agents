# Robustness Bundle Implementation Plan

## Objective
Implement a suite of robustness features to harden the `btc-laptop-agents` system for autonomous, crash-resistant execution. This bundle includes configuration validation, risk controls, idempotency, realistic paper trading simulation (fees, partial fills), state persistence, and strict session limits.

## Phase 1: Configuration & Safety Gates
**Goal**: Fail fast if configuration is invalid and enforce risk limits during execution.

### Step 1.1: Environment & Config Validation
**Target**: `src/laptop_agents/run.py`, `src/laptop_agents/core/validation.py` (New)

1.  Create `src/laptop_agents/core/validation.py`.
2.  Implement `validate_config(args, strategy_config)` function.
    *   Check for required env vars (`BITUNIX_API_KEY`, etc.) if mode is `live` or `live-session`.
    *   Validate `risk_pct` (0.1% - 5%), `stop_bps` (> 5), `max_leverage` (< 20).
    *   Validate strategy config structure if provided.
3.  Update `src/laptop_agents/run.py` to call `validate_config` at the start of `main()`.

### Step 1.2: Risk Gate Middleware
**Target**: `src/laptop_agents/paper/broker.py`, `src/laptop_agents/execution/bitunix_broker.py` (if applicable)

1.  Define Risk Constants in `src/laptop_agents/core/hard_limits.py` (or ensure existing ones are sufficient):
    *   `MAX_POSITION_SIZE_USD`
    *   `MAX_DAILY_LOSS_PCT`
    *   `MAX_ORDERS_PER_MINUTE`
2.  Update `PaperBroker` (and `BitunixBroker` if possible) to check these limits *before* placing an order.
    *   Implement rate limiting (orders per minute).
    *   Check `MAX_DAILY_LOSS` against `current_equity - starting_equity`.

### Step 1.3: Idempotency (Order UUIDs)
**Target**: `src/laptop_agents/session/timed_session.py`, `src/laptop_agents/paper/broker.py`

1.  Update `PaperBroker._try_fill` to accept a `client_order_id`.
2.  Maintain a `processed_order_ids` set in `PaperBroker`.
3.  If `client_order_id` is already in the set, log "Duplicate Ignored" and return `None`.
4.  Update `timed_session.py` to generate a deterministic UUID for the signal if possible, or a random one, and pass it to `broker.on_candle`.

## Phase 2: Realistic Paper Trading
**Goal**: Make paper trading results match reality closer by simulating fees and liquidity constraints.

### Step 2.1: Real-Time Fee Simulation
**Target**: `src/laptop_agents/paper/broker.py`

1.  Verify `fees_bps` is passed to `PaperBroker`.
2.  Ensure `_try_fill` (entry) and `_exit` (exit) calculate and deduct fees from PnL.
    *   Formula: `fee_usd = notional_usd * (fees_bps / 10000)`.
    *   Net PnL = Gross PnL - Entry Fee - Exit Fee.

### Step 2.2: Partial Fill Simulation
**Target**: `src/laptop_agents/paper/broker.py`

1.  In `_try_fill`:
    *   Check `candle.volume` (if available, defaulting to infinite if 0).
    *   If `order_qty > candle.volume * 0.1` (10% of bar volume):
        *   Fill only `candle.volume * 0.1` in this step.
        *   Create a "pending partial order" state.
        *   (Simplification for Bundle): Alternatively, reject order or cap size to 10% of volume and log "Partial Fill via Cap".
        *   *Plan Choice*: Cap the fill at 10% of volume. If the user wanted "split fill over time", that requires complex state management. For this "Robustness" pass, capping/partial-fill-event for the *available liquidity* is the first step.
    *   Emit `PartialFill` event.

## Phase 3: Persistence & Lifecycle
**Goal**: Ensure the agent can crash and restart without losing money or state.

### Step 3.1: State Persistence (Checkpoints)
**Target**: `src/laptop_agents/paper/broker.py`

1.  Add `state_path` to `PaperBroker.__init__`.
2.  Implement `_save_state()`: writes `current_positions`, `equity`, `order_history` to `state.json` (atomic write).
3.  Implement `_load_state()`: loads from `state.json` on init.
4.  Call `_save_state()` after every Fill or Exit.

### Step 3.2: Strict Timed-Session Shutdown
**Target**: `src/laptop_agents/session/timed_session.py`

1.  Existing logic has `end_time = start_time + (duration_min * 60)`.
2.  Add a generic `TimeLimitExceeded` check inside the loop.
3.  Ensure `GracefulShutdown` context manager forces a clean exit (logging "Session Complete: Duration Limit Reached").
4.  Ensure `broker.close_all()` is called on exit (to flatten inventory).

## Phase 4: Performance & Stability
**Goal**: Prevent memory growth during long sessions.

### Step 4.1: Memory Leak Prevention
**Target**: `src/laptop_agents/session/timed_session.py`

1.  Currently, `load_bitunix_candles` returns a fresh list.
2.  The potential leak is `append_event` keeping `events` in memory or `Supervisor` growing.
3.  Ensure `append_event` in `orchestrator.py` only writes to file and does *not* keep a growing list in memory (or clears it periodically).
4.  If `candles` list in `state` needs simple "recent" history, ensure we aren't passing `candles=all_history` if `all_history` grows indefinitely.
    *   *Correction*: `limit` in `load_bitunix_candles` limits the list size. So `candles` list size is bounded by `limit` (e.g. 200).
    *   The issue might be `equity_history` list in `orchestrator.py` or similar. Bounded `deque` usage for `equity_history` if checking "Max Drawdown" over time is needed.
    *   Action: Review `timed_session.py` for any unbounded lists (e.g., `result.events`?).
        *   `result.events` grows with every event. For 10 mins, it's fine. For 24h, it's a leak.
        *   Change `SessionResult.events` to not store *all* events, or optionally disable event storage in memory (just rely on file log).

## Execution Instructions
1.  **Read** each target file.
2.  **Apply** changes for Phase 1 (Validation).
3.  **Apply** changes for Phase 2 (Broker).
4.  **Apply** changes for Phase 3 (Persistence).
5.  **Apply** changes for Phase 4 (Performance).
6.  **Verify** by running `python src/laptop_agents/run.py --mode selftest` or a short 1-min backtest.
