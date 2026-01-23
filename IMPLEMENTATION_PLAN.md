# Audit Remediation: Autonomous Implementation Plan (Updated)

> **Source**: 4564af6f-2ccc-43ef-8f1f-5d6bf4c013ff/implementation_plan.md
> **Execution Status**: In Progress

---

## Phase 1: Dead Code Purge [FINISHED]
**Status**: 100% Complete
- [x] Delete `src/laptop_agents/prompts/` directory
- [x] Delete `src/laptop_agents/alerts/` directory  
- [x] Verify no imports reference deleted modules
- [x] Run `/go` workflow

---

## Phase 2: Documentation & Gitignore Fixes [FINISHED]
**Status**: 100% Complete
- [x] Update `README.md`: Python 3.12+ -> 3.11+
- [x] Update `README.md`: YAML -> JSON for config references
- [x] Add `*.db`, `testall-report.*` to `.gitignore`
- [x] Remove tracked test artifacts from repo (`test_state_broker.db`, `testall-report.*`)
- [ ] Run `/go` workflow

---

## Phase 3: Dependency Cleanup [FINISHED]
**Status**: 100% Complete (pip install succeeded; warnings noted)
- [x] Remove `websockets` from `pyproject.toml`
- [x] Generate `requirements.lock` via `uv pip compile`
- [x] Verify clean `pip install -e .`
- [ ] Run `/go` workflow

---

## Phase 4: Tooling Unification (Ruff) [FINISHED]
**Status**: 100% Complete
- [x] Replace `.pre-commit-config.yaml` with ruff-only config
- [x] Add `ruff check` and `ruff format --check` to CI workflow before mypy
- [x] Remove black/flake8 references
- [ ] Run `/go` workflow

---

## Phase 5: Scripts Cleanup [FINISHED]
**Status**: 100% Complete
- [x] Create `scripts/archive/` directory
- [x] Move `scripts/monte_carlo_v1.py` and `scripts/optimize_strategy.py` into archive
- [x] Delete `la.ps1`
- [x] Add `scripts/README.md` documenting canonical scripts table
- [ ] Run `/go` workflow

---

## Phase 6: Config Mutable Default Fix [FINISHED]
**Status**: 100% Complete
- [x] In `core/config.py`, change `params: Dict[str, Any] = {}` to `params: Dict[str, Any] = Field(default_factory=dict)` and import `Field`
- [x] Verify no remaining mutable dict defaults
- [ ] Run `/go` workflow

---

## Phase 7: CLI Argparse Removal [FINISHED]
**Status**: 100% Complete
- [x] Remove argparse usage from `commands/session.py`; convert to Typer options
- [x] Ensure `la run --help` lists all options (not yet re-verified in this run)
- [ ] Run `/go` workflow

---

## Phase 8: Circuit Breaker Consolidation [FINISHED]
**Status**: 100% Complete
- [x] Find all usages of `TradingCircuitBreaker`
- [x] Replace with `ErrorCircuitBreaker`, update method calls
- [x] Delete `resilience/circuit.py`
- [x] Update `resilience/__init__.py` exports

---

## Phase 9: Rate Limiter Consolidation [FINISHED]
**Status**: 100% Complete
- [x] Verify `core/rate_limiter.py` is canonical
- [x] Delete `resilience/rate_limiter.py`
- [x] Update all imports to use `core/rate_limiter.py`

---

## Phase 10: Unified Resilience Module [FINISHED]
**Status**: 100% Complete
- [x] Create `core/resilience.py` re-exporting consolidated classes
- [x] Update all imports throughout codebase
- [x] Deprecate old `resilience/` imports
- [ ] Run `/go` workflow

---

## Phase 11: God Module Refactor - Heartbeat [FINISHED]
**Status**: 100% Complete
- [x] Create `session/heartbeat.py` with extracted `heartbeat_task()`
- [x] Update `async_session.py` to import from new module
- [ ] Run full test suite
- [ ] Run `/go` workflow

---

## Phase 12: God Module Refactor - State [IN PROGRESS]
**Status**: Partial (line-count target not met)
- [x] Create `session/session_state.py` with state management logic
- [x] Update `async_session.py` to delegate to new module
- [ ] Verify `async_session.py` line count reduced by 30%+ (current ~1605 lines)
- [ ] Run full test suite
- [ ] Run `/go` workflow

---

## Phase 13: HTTP Library Consolidation (Optional)
**Status**: Pending
- [ ] Replace `aiohttp` WebSocket with `httpx` in `bitunix_ws.py`
- [ ] Remove `aiohttp` from dependencies
- [ ] Run full test suite
- [ ] Run `/go` workflow

---

## Phase 14: Final Verification & Walkthrough
**Status**: Pending
- [ ] Run comprehensive verification suite
- [ ] Generate `walkthrough.md` documenting all changes
- [ ] Verify GitHub Actions CI green
- [ ] Create PR summary

---

## NEXT STEPS
1.  Extract heartbeat logic from `async_session.py` (Phase 11).
2.  Extract session state management (Phase 12).
3.  Decide on optional HTTP consolidation (Phase 13).
