# Async Real-Time & Resilience Plan

## Objective
Upgrade the `btc-laptop-agents` system from a synchronous REST polling loop to a high-performance **asyncio** engine with **WebSocket** market data ingestion, connection resilience, and sub-second trade monitoring.

## Phase 1: Async Infrastructure (The Foundation)
**Target**: `src/laptop_agents/session/async_session.py` (New), `src/laptop_agents/run.py`

1.  **Create `AsyncRunner` Class**:
    *   Design a new `AsyncRunner` that orchestrates the event loop.
    *   Use `asyncio.Queue` for passing events (Ticks, Candles, Signals) between components.
2.  **Migration Strategy**:
    *   Do NOT overwrite `timed_session.py` immediately. Create a parallel `src/laptop_agents/session/async_session.py`.
    *   Expose `run_async_session(...)` as the entry point.
    *   Update `src/laptop_agents/run.py` to `import run_async_session` if `args.async_mode` is set (or just default to it for `live-session`).

## Phase 2: WebSocket Data Ingestion
**Target**: `src/laptop_agents/data/providers/bitunix_ws.py` (New)

1.  **Implement `BitunixWSProvider`**:
    *   Use `websockets` or `aiohttp` library.
    *   Method `connect()`: Authenticate (if private) and handle connection handshake.
    *   Method `subscribe_kline()`: Subscribe to 1m candle updates.
    *   Method `subscribe_ticker()`: Subscribe to real-time `bookTicker` for BBO (Best Bid/Offer).
    *   Method `listen()`: Async generator that yields standardized `Tick` or `Candle` objects.
2.  **Resilience (Auto-Reconnect)**:
    *   Wrap the `listen()` loop in `tenacity` retry logic.
    *   On disconnect: Log "Connection Lost", pause trading, wait with exponential backoff, reconnect, and resubscribe.

## Phase 3: Concurrent Execution & Watchdog
**Target**: `src/laptop_agents/session/async_session.py`

1.  **Main Event Loop**:
    *   Use `asyncio.gather(market_data_task(), watchdog_task(), strategy_task(), heartbeat_task())`.
2.  **Strategy Task**:
    *   Wait for *confirmed* 1m candle closures from WebSocket.
    *   Run the `Supervisor` (strategy logic) in a thread executor (if it remains synchronous/CPU-heavy) or directly if lightweight.
3.  **Sub-Minute Watchdog (The "Guardian")**:
    *   A dedicated async task running every 100ms.
    *   Checks current `Broker.pos` against the *latest* ticker price.
    *   If `price <= SL` or `price >= TP` (for Long), trigger `Broker.exit()` immediately.
    *   *Why*: Eliminates the "blind spot" between 1-minute candles.

## Phase 4: Integration
**Target**: `src/laptop_agents/paper/broker.py`, `src/laptop_agents/run.py`

1.  **Broker Update**: ensure `PaperBroker` methods are thread-safe or async-compatible (synchronous is fine if called sequentially from the loop).
2.  **CLI Integration**:
    *   Add `--async` flag to `run.py`.
    *   Example: `python run.py --mode live-session --async --source bitunix`.

## Execution Steps for the Agent
1.  **Install Deps**: Run `pip install websockets aiohttp tenacity` (if missing).
2.  **Code**: Create `bitunix_ws.py`.
3.  **Code**: Create `async_session.py` implementing the `asyncio` loop with proper signal handling (SIGINT).
4.  **Integration**: Wire it up in `run.py`.
5.  **Verify**: Run a 60-second test session connecting to Bitunix (public stream) to verify tick flow.

## Constraints
*   **No "time.sleep()"**: All delays must use `await asyncio.sleep()`.
*   **Fail Fast**: If WebSocket auth fails or connection is refused 3x, exit the process non-zero.
