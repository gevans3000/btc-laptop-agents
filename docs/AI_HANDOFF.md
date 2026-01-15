# AI_HANDOFF.md — Agent Context Loading

> **Status**: ACTIVE

> **Audience**: AI Agents starting a session.

## Context Loading Order
1.  **Read `docs/START_HERE.md`** (Map of the world).
2.  **Read `docs/SPEC.md`** (The Law).
3.  **Read `docs/DEV_AGENTS.md`** (Your constraints).
4.  **Check `task.md`** (Current objectives, if present).

## Architecture Summary
- **CLI**: `src/laptop_agents/run.py` - Thin wrapper, delegates to orchestrator.
- **Orchestrator**: `src/laptop_agents/core/orchestrator.py` - Coordinates all modes.
- **Async Session**: `src/laptop_agents/session/async_session.py` - High-performance event-driven engine.
- **Brokers**: `PaperBroker` (simulation), `BitunixBroker` (live).
- **WS Provider**: `src/laptop_agents/data/providers/bitunix_ws.py` - Real-time market data.
- **Hard Limits**: `src/laptop_agents/core/hard_limits.py` - Immutable safety constraints.

## Key Concepts
1. **Execution Mode**: `--execution-mode paper` vs `live` determines broker selection.
2. **Engine Selection**: `--async` flag enables the high-performance WebSocket engine.
3. **Data Source**: `--source mock` vs `bitunix` determines candle source.
4. **Safety**: Hard limits are enforced at the broker level and cannot be bypassed.
5. **Kill Switch**: `config/KILL_SWITCH.txt` blocks all order placement.

## Recent Changes
- Implemented **Async Engine** (`asyncio` + WebSockets) for sub-second market data responsiveness.
- Added Live Trading System (Dynamic sizing implemented).
- Added `cancel_order`, `cancel_all_orders` to BitunixFuturesProvider.
- Added `shutdown()` method for graceful cleanup (cancels orders + closes positions).
- Added `execution_mode` parameter to `timed_session.py`.
- Refactored `exec_engine.py` to modular `trading/exec_engine.py` (Live Loop).

## Verification
Always run `.\scripts\verify.ps1` or `python scripts/test_live_system.py` before finalizing changes.


