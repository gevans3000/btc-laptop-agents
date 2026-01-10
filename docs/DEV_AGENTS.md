# DEV_AGENTS.md — Rules for AI Agents

> **AUDIENCE**: AI Coding Assistants (Gemini, Roo, Codex, etc.)
> **PURPOSE**: Standards for safely modifying this repo.

## 1. The Prime Directive
**Do not break the `verify.ps1` loop.**
Every change must pass `.\scripts\verify.ps1 -Mode quick` before you request user review.

## 2. Monolith Awareness
*   **The Code**: The system is currently a Monolith in `src/laptop_agents/run.py`.
*   **The Trap**: Do not edit files in `src/laptop_agents/agents/` to fix bugs. They are not wired. Edit `run.py` instead.
*   **The Future**: We will refactor later. For now, respect the monolith.

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
Certain areas of the monolith are critical for stability. Do not modify these without explicit confirmation:
*   **Core Loop Timing**: Logic in `run_live_paper_trading` handling sleep/intervals.
*   **Risk Math**: Mathematical formulas in `calculate_position_size`.
*   **Artifact Schemas**: Global constants defining `REQUIRED_TRADE_COLUMNS`.

## 7. Reporting & Handoff
To ensure "agent-readiness" for the next session:
1.  **Update `task.md`**: Summarize what you did AND the result of `verify.ps1`.
2.  **Provide Proof**: In your final report, state specifically which modes were tested (e.g., "Verified via `mode=mock` and `mode=selftest`").
3.  **Check for Drift**: If you change logic, check if `docs/MAP.md` line ranges need updating.

