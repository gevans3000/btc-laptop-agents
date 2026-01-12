# AI_HANDOFF.md — Agent Context Loading

> **Audience**: AI Agents starting a session.

## Context Loading Order
1.  **Read `docs/START_HERE.md`** (Map of the world).
2.  **Read `docs/SPEC.md`** (The Law).
3.  **Read `docs/DEV_AGENTS.md`** (Your constraints).
4.  **Check `task.md`** (Current objectives, if present).

## Active Constraints & Reminders
*   **Modular Architecture**: The codebase uses a modular design:
    *   `src/laptop_agents/run.py` — Thin CLI wrapper (~100 lines).
    *   `src/laptop_agents/core/orchestrator.py` — Main coordination logic.
    *   `src/laptop_agents/data/loader.py` — Candle fetching (mock/bitunix).
    *   `src/laptop_agents/trading/exec_engine.py` — Live paper trading engine.
    *   `src/laptop_agents/trading/signal.py` — Signal generation with ATR filter.
*   **Verify**: Always run `.\scripts\verify.ps1 -Mode quick` before finishing.
*   **Drift**: Do not assume docs are perfect, but assume `SPEC.md` is intended to be true. Fix it if it's wrong.
*   **No Sync Pack**: The `assistant_sync_pack.md` and `make_sync_pack.ps1` have been removed. They are not needed.
