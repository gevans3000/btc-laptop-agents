# AGENTS.md — Collaboration Architecture

## Wiring Status (v1.1 Modular Beta)

> **UPDATE**: The system now supports a **MODULAR PIPELINE** in Orchestrated mode.

*   **Stable Implementation**: `src/laptop_agents/run.py` still contains the original monolithic logic for basic backtests and single runs.
*   **Orchestrated Mode (`--mode orchestrated`)**: Successfully wires the modular agents in `src/laptop_agents/agents/` into a single E2E pass.
*   **Active Modular Agents**:
    *   `MarketIntakeAgent`: Data normalization.
    *   `DerivativesFlowsAgent`: Funding & OI snapshots.
    *   `SetupSignalAgent`: Trend Ribbon + Sweep logic.
    *   `ExecutionRiskSentinelAgent`: Risk sizing & safety gates.
    *   `JournalCoachAgent`: Trade logging.

## Logical Roles
Even within the `run.py` monolith, we observe these logical roles:

1.  **Supervisor**: The main loop in `run_live_paper_trading()`. Handles scheduling and file I/O.
2.  **Market Intake**: `load_..._candles()` functions.
3.  **Signal**: `generate_signal()` and SMA logic.
4.  **Execution/Risk**: `calculate_position_size()` and `simulate_trade_one_bar()`.

## Future Vision (v1.1+)
Eventually, the monolith will break into the independent agents described below, orchestrated by a queue-based harness. **This is not current reality.**

*(Original content below preserved for v1.1 planning)*

## Non-negotiables
- Paper-only. Never place real orders.
- Minimal diffs. No refactors/renames unless required.
- No hangs: any network call must have timeouts.
- Always validate: `python -m compileall src` and `pytest -q`
- Persist artifacts:
  - logs/events.jsonl (ops + resilience)
  - data/paper_journal.jsonl (paper actions)
  - data/paper_state.json (state)
  - data/control.json (pause/extend)

## Logical agents (implementation can be functions/modules)
1) Supervisor (Loop owner): scheduling + exception boundary + heartbeat
2) Market Intake: provider fetch (Bitunix) using resilience wrapper
3) Setup/Signal: deterministic rules (EMA/ATR thresholds)
4) Execution/Risk (paper): sim fills + position mgmt + stats
5) Journal Coach: concise notes per loop/trade (optional)
