# Audit Remediation: Implementation Plan

## Overview

All 14 phases of audit remediation from `AUDIT_REPORT_2026.md` are complete (13 executed, 1 skipped). The codebase now has unified resilience primitives, a modular session architecture (64% reduction in `async_session.py`), Ruff-enforced linting, and Typer-based CLI. No remaining work exists. This document serves as a reference for future maintainers.

---

## Progress Snapshot

### Latest 2 Completed

| Phase | Description | Key Outcome |
|-------|-------------|-------------|
| **14** | Final Verification & Walkthrough | Pytest, Mypy, Ruff, Doctor all green; `walkthrough.md` generated |
| **12** | God Module Refactor - State Extraction | `async_session.py` reduced 1605 → 566 lines; state logic in `session/session_state.py` |

---

## Architecture & Maintainability Targets

### Module Boundaries

| Module | Ownership |
|--------|-----------|
| `core/resilience.py` | Exports `CircuitBreaker`, `RateLimiter`, `retry_with_backoff`. Single source of truth. |
| `session/async_session.py` | Orchestrates run loop. Delegates heartbeat, funding, execution, state to submodules. |
| `session/heartbeat.py` | Periodic status logging. |
| `session/funding.py` | Funding rate polling. |
| `session/execution.py` | Order placement helpers. |
| `session/session_state.py` | `AsyncSessionResult` dataclass and state transitions. |
| `commands/session.py` | CLI entry point via Typer. No argparse. |

### Interfaces/Contracts

- **Resilience**: All code imports from `laptop_agents.core.resilience`. Direct imports from `resilience/` submodules are deprecated.
- **Configuration**: Pydantic models with `Field(default_factory=...)` for mutables. No bare `= {}`.
- **CLI**: All commands exposed via Typer. `la --help` is the contract surface.

### Error Handling/Logging Strategy

- Unhandled exceptions bubble to `async_session.py` run loop, logged via `structlog`.
- Circuit breakers wrap external calls (exchange API, WebSocket).
- All log calls include `component=` for filtering.

### Configuration Strategy

- `config.json` is the runtime config. Schema defined in `core/config.py`.
- Environment variables override config via Pydantic `env` support.

### Testing Strategy

| Type | Location | Command |
|------|----------|---------|
| Unit | `tests/unit/` | `pytest tests/unit/` |
| Integration | `tests/integration/` | `pytest tests/integration/` |
| Smoke | `la doctor --fix` | Validates runtime health |

---

## Phased Plan

### Phase Status: ALL COMPLETE

No phases remain. Summary of executed phases:

| # | Phase | Status |
|---|-------|--------|
| 1 | Dead Code Purge | ✅ |
| 2 | Documentation & Gitignore | ✅ |
| 3 | Dependency Cleanup | ✅ |
| 4 | Tooling Unification (Ruff) | ✅ |
| 5 | Scripts Cleanup | ✅ |
| 6 | Config Mutable Default Fix | ✅ |
| 7 | CLI Argparse Removal | ✅ |
| 8 | Circuit Breaker Consolidation | ✅ |
| 9 | Rate Limiter Consolidation | ✅ |
| 10 | Unified Resilience Module | ✅ |
| 11 | Heartbeat Extraction | ✅ |
| 12 | State Extraction | ✅ |
| 13 | HTTP Consolidation | ⏭️ Skipped |
| 14 | Final Verification | ✅ |

**Phase 13 Skip Reason**: `bitunix_ws.py` was already merged into `bitunix_futures.py`. Replacing aiohttp would require architectural changes beyond audit scope. Tracked as deferred debt.

---

## Notes for Autonomous Execution

### How to Proceed Safely

Since all phases are complete, no autonomous execution is needed. For future remediation:

1. Read `AUDIT_REPORT_2026.md` for context.
2. Identify the specific finding to address.
3. Create a new phase in this document with: Goal, Steps, Dependencies, Failure Modes, Validation, Commit Checkpoint.
4. Execute incrementally, running `/go` after each step.
5. Update `task.md` to track progress.

### If References Conflict with Active Plan

Active files (`task.md`, `IMPLEMENTATION_PLAN.md`) are authoritative. Reference files in `brain/4564af6f.../` are read-only historical snapshots. If conflict arises, trust active files and document the divergence.

### When to Stop/Re-evaluate

- Any test failure blocks further progress.
- Any mypy error blocks further progress.
- Structural changes to `async_session.py` require full test suite pass before commit.

---

## Commit History Reference

| Phase | Commit Message |
|-------|----------------|
| 1 | `chore: remove dead prompts/ and alerts/ modules` |
| 2 | `docs: fix Python version, config format, gitignore` |
| 3 | `chore(deps): remove websockets, add lockfile` |
| 4 | `chore(tooling): migrate to ruff` |
| 5 | `chore(scripts): archive deprecated, document canonical` |
| 6 | `fix(config): use Field(default_factory) for params` |
| 7 | `fix(cli): port all args to Typer` |
| 8 | `refactor(resilience): consolidate circuit breakers` |
| 9 | `refactor(resilience): consolidate rate limiters` |
| 10 | `refactor: unified resilience module in core` |
| 11 | `refactor(session): extract heartbeat module` |
| 12 | `refactor(session): extract state module` |
| 14 | `docs: finalize audit remediation` |
