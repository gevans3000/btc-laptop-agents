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
- [ ] Run `/go` workflow

## Phase 3: Dependency Cleanup [AFTER PHASE 2]
- [ ] Drop `websockets` dependency from `pyproject.toml`
- [ ] Generate `requirements.lock` with `uv pip compile`
- [ ] `pip install -e .` succeeds
- [ ] Run `/go` workflow

## Phase 4: Tooling Unification (Ruff) [READY]
- [ ] Replace `.pre-commit-config.yaml` with ruff-only hooks
- [ ] Add `ruff check` + `ruff format --check` to CI before mypy
- [ ] Remove black/flake8 mentions
- [ ] Run `/go` workflow

## Phase 5: Scripts Cleanup [READY]
- [ ] Create `scripts/archive/`; move `monte_carlo_v1.py`, `optimize_strategy.py`
- [ ] Delete `la.ps1`
- [ ] Add `scripts/README.md` with canonical tools table
- [ ] Run `/go` workflow

## Phase 6: Config Mutable Default Fix [READY]
- [ ] In `core/config.py`, change `params: Dict[str, Any] = {}` -> `Field(default_factory=dict)` and import `Field`
- [ ] Verify no mutable dict defaults remain
- [ ] Run `/go` workflow

## Phase 7: CLI Argparse Removal [BLOCKED on Phase 6]
- [ ] Replace argparse in `commands/session.py` with Typer options
- [ ] Confirm `la run --help` shows options
- [ ] Run `/go` workflow

## Phase 8: Circuit Breaker Consolidation [FINISHED]
- [x] Find all `TradingCircuitBreaker` usages
- [x] Replace with `ErrorCircuitBreaker`
- [x] Delete `resilience/circuit.py`

## Phase 9: Rate Limiter Consolidation [FINISHED]
- [x] Verify `core/rate_limiter.py` canonical status
- [x] Delete `resilience/rate_limiter.py`
- [x] Update imports to `core/rate_limiter.py`
