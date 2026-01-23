# Audit Remediation: Autonomous Phase Checklist

## Phase 1: Dead Code Purge [FINISHED]
- [x] Delete `src/laptop_agents/prompts/`
- [x] Delete `src/laptop_agents/alerts/`
- [x] Verify no imports reference deleted modules
- [x] Run `/go` workflow

## Phase 2: Documentation & Gitignore Fixes [FINISHED]
- [x] Update `README.md` Python version (3.12 -> 3.11)
- [x] Update `README.md` config format (YAML -> JSON)
- [x] Add `*.db`, `testall-report.*` to `.gitignore`
- [x] Remove legacy artifacts (`test_state_broker.db`, `testall-report.*`)
- [x] Run `/go` workflow

## Phase 3: Dependency Cleanup [FINISHED]
- [x] Drop `websockets` dependency from `pyproject.toml`
- [x] Generate `requirements.lock` with `uv pip compile`
- [x] `pip install -e .` succeeds
- [x] Run `/go` workflow

## Phase 4: Tooling Unification (Ruff) [FINISHED]
- [x] Replace `.pre-commit-config.yaml` with ruff-only hooks
- [x] Add `ruff check` + `ruff format --check` to CI before mypy
- [x] Remove black/flake8 mentions
- [x] Run `/go` workflow

## Phase 5: Scripts Cleanup [FINISHED]
- [x] Create `scripts/archive/`; move `monte_carlo_v1.py`, `optimize_strategy.py`
- [x] Delete `la.ps1`
- [x] Add `scripts/README.md` with canonical tools table
- [x] Run `/go` workflow

## Phase 6: Config Mutable Default Fix [FINISHED]
- [x] Change `params: Dict[str, Any] = {}` -> `Field(default_factory=dict)` and import `Field`
- [x] Verify no mutable dict defaults remain
- [x] Run `/go` workflow

## Phase 7: CLI Argparse Removal [FINISHED]
- [x] Replace argparse in `commands/session.py` with Typer options
- [x] Confirm `la run --help` shows options
- [x] Run `/go` workflow

## Phase 8: Circuit Breaker Consolidation [FINISHED]
- [x] Find all `TradingCircuitBreaker` usages
- [x] Replace with `ErrorCircuitBreaker`
- [x] Delete `resilience/circuit.py`
- [x] Run `/go` workflow

## Phase 9: Rate Limiter Consolidation [FINISHED]
- [x] Verify `core/rate_limiter.py` canonical status
- [x] Delete `resilience/rate_limiter.py`
- [x] Update imports to `core/rate_limiter.py`
- [x] Run `/go` workflow

## Phase 10: Unified Resilience Module [FINISHED]
- [x] Create `core/resilience.py` re-exporting consolidated classes
- [x] Update imports to use `core/resilience.py`
- [x] Run `/go` workflow

## Phase 11: God Module Refactor - Heartbeat [FINISHED]
- [x] Extract `heartbeat_task()` into `session/heartbeat.py`
- [x] Update `async_session.py` to import the new module
- [x] Run full tests
- [x] Run `/go` workflow

---

## Phase 12: God Module Refactor - State [TODO]
- [x] Extract session state logic into `session/session_state.py`
- [ ] Extract additional logic to reduce `async_session.py` by 30%+ (~1605 -> <1300 lines)
- [ ] Run full tests
- [ ] Run `/go` workflow

## Phase 13: HTTP Library Consolidation [SKIPPED]
> Deferred: `bitunix_ws.py` not present; would require significant refactor.

## Phase 14: Final Verification & Walkthrough [TODO]
- [ ] Run comprehensive verification suite (`pytest`, `mypy`, `ruff`, `la doctor`)
- [x] Generate `walkthrough.md`
- [ ] Verify GitHub Actions CI green
- [x] Create PR summary
