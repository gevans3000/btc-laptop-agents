# DEV_AGENTS.md — Rules for AI Agents

> **Status**: ACTIVE

> **AUDIENCE**: AI Coding Assistants (Gemini, Roo, Codex, etc.)
> **PURPOSE**: Standards for safely modifying this repo.

## 1. The Prime Directive
**Do not break the `verify.ps1` loop.**
Every change must pass `.\scripts\verify.ps1 -Mode quick` before you request user review.

## 2. Modular Awareness
*   **The Code**: The system has transitioned from a monolith to a modular architecture.
*   **The Structure**:
    *   `src/laptop_agents/run.py`: Orchestrator and CLI entry point.
    *   `src/laptop_agents/trading/exec_engine.py`: Live/Paper execution engine.
    *   `src/laptop_agents/backtest/engine.py`: Backtesting and validation.
    *   `src/laptop_agents/agents/`: Modular agents (Supervisor, State, Setups).
*   **The Goal**: Maintain modular isolation. Fix bugs in the specific modules, not the orchestrator.

## 3. Documentation "Law"
*   **Read `docs/SPEC.md`**: This is the current truth.
*   **Update Responsibility**: If you change CLI args or output schemas, you **MUST** update `SPEC.md` in the same PR.

## 4. Workflow Strictness
1.  **Read First**: Always scan `run.py` outline and `SPEC.md` before coding.
2.  **Small Diffs**: Limit changes to < 50 lines if possible.
3.  **No Refactors**: Do not rename functions or split files "for cleanliness" without explicit user instruction.
4.  **Artifact Respect**: Never change the schema of `events.jsonl` or `trades.csv` (append-only compatible additions are allowed).

## 5. Verification Checklist
Before finishing your turn:
- [ ] Ran `.\scripts\verify.ps1`?
- [ ] Updated `docs/SPEC.md` if args changed?
- [ ] checked `logs/live.err.txt`?

## 6. Dangerous Zones
Certain areas of the core engine are critical for stability. Do not modify these without explicit confirmation:
*   **Core Loop Timing**: Logic in `run_live_paper_trading` handling sleep/intervals.
*   **Risk Math**: Mathematical formulas in `calculate_position_size`.
*   **Artifact Schemas**: Global constants defining `REQUIRED_TRADE_COLUMNS`.

## 7. Reporting & Handoff
To ensure "agent-readiness" for the next session:
1.  **Update `task.md`**: Summarize what you did AND the result of `verify.ps1`.
2.  **Provide Proof**: In your final report, state specifically which modes were tested (e.g., "Verified via `mode=mock` and `mode=selftest`").
3.  **Check for Drift**: If you change logic, check if `docs/MAP.md` line ranges need updating.


## 8. Git Commit Policy
### Frequency
*   **ALWAYS** commit changes immediately after completing a logical unit of work.
*   **NEVER** wait for multiple tasks to pile up before committing.
*   If you refactor a file and then add a feature, that must be **two separate commits**.

### Commit Message Format
*   Use Semantic Commit messages (e.g., `feat:`, `fix:`, `refactor:`, `docs:`).
*   Keep descriptions concise but specific.

### Workflow
1.  Make code changes.
2.  Verify the changes (run tests or lint).
3.  Stage specific files (`git add <file>`).
4.  Commit immediately (`git commit -m "..."`).


