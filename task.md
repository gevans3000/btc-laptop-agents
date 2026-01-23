# Audit Remediation Task Tracker

## Current Status

**Status**: ✅ ALL PHASES COMPLETE (13/14 executed, 1 skipped)

### Latest 2 Completed

1. **Phase 14: Final Verification & Walkthrough** — Ran comprehensive verification suite (Pytest, Mypy, Ruff, Doctor), generated `walkthrough.md`, verified CI logic.
   *Ref: Phase 14 in `brain/4564af6f.../task.md`*

2. **Phase 12: God Module Refactor - State Extraction** — Extracted `AsyncSessionResult`, `funding_task()`, order execution helpers into separate modules. Reduced `async_session.py` from 1605 → 566 lines (64% reduction).
   *Ref: Phase 12 in `brain/4564af6f.../task.md`*

### In Progress

None

---

## Remaining Work (Phased)

**No remaining phases.** All audit remediation items are complete.

Phase 13 (HTTP Library Consolidation) was explicitly skipped because `bitunix_ws.py` was merged into `bitunix_futures.py`, eliminating the need for aiohttp replacement.

---

## Maintainability Guidelines

These conventions were established during remediation and must be followed for future work:

| Area | Convention |
|------|------------|
| **Naming** | Snake_case for modules/functions, PascalCase for classes. No abbreviations except `ws` (WebSocket). |
| **Resilience** | Import from `core/resilience.py` only. Do not create new circuit breakers or rate limiters elsewhere. |
| **Config** | Use `Field(default_factory=...)` for mutable defaults. Never `= {}` or `= []`. |
| **Logging** | Use `structlog` via existing patterns in `core/logger.py`. Include `component=` context. |
| **Testing** | Unit tests in `tests/unit/`, integration in `tests/integration/`. Name pattern: `test_<module>_<behavior>.py`. |
| **Commits** | Semantic format: `feat|fix|chore|refactor|docs(scope): message`. One logical change per commit. |
| **Verification** | Run `/go` workflow after every phase. Never commit broken code. |

---

## Guardrails

| Constraint | Rationale |
|------------|-----------|
| Do not touch `core/resilience.py` exports | Central resilience contract for the codebase |
| Do not add new dependencies without lockfile update | `requirements.lock` must stay in sync |
| Do not reintroduce `argparse` | CLI uses Typer exclusively |
| Do not create files in `prompts/` or `alerts/` | These directories were purged as dead code |
| Phase 13 is deferred technical debt | Track in backlog, not active remediation |

---

## Success Criteria (All Met)

- [x] Zero dead code modules
- [x] Zero duplicate resilience implementations
- [x] `async_session.py` reduced 30%+ (actual: 64%)
- [x] README matches CI (Python 3.11+)
- [x] All tests pass (1 stress-test exempt)
- [x] `la run --help` shows all options
