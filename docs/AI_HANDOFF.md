# AI_HANDOFF.md — Sync Pack Context

> **Audience**: AI Agents starting a session.

## IMPORTANT: The Sync Pack
The file `assistant_sync_pack.md` in the root is a **GENERATED ARTIFACT**.
*   **Do not edit it manually.**
*   It serves as a snapshot of the system state (File tree, recent logs, config dump).
*   If it is missing or stale, generate it using `scripts/generate_sync_pack.ps1` (Forward looking - functionality to be added).

## Context Loading Order
1.  **Read `docs/START_HERE.md`** (Map of the world).
2.  **Read `docs/MVP_SPEC.md`** (The Law).
3.  **Read `docs/DEV_AGENTS.md`** (Your constraints).
4.  **Check `task.md`** (Current objectives).

## Active Constraints & Reminders
*   **Monolith**: Work in `src/laptop_agents/run.py`.
*   **Verify**: Always run `verify.ps1`.
*   **Drift**: Do not assume docs are perfect, but assume `MVP_SPEC` is intended to be true. Fix it if it's wrong.