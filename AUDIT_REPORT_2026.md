# Repository Audit Report: btc-laptop-agents

**Date**: 2026-01-23
**Auditor**: Antigravity (Senior Software Architect)

## Executive Summary

- **Reliability vs. Debt Paradox**: The system features institutional-grade safety (zombie detection, atomic persistence) but suffers from significant technical debt: duplicate core components (Circuit Breakers, Rate Limiters), a "God Module" (`async_session.py`), and conflicting documentation.
- **Critical Code Duplication**: Essential resilience primitives (`CircuitBreaker`, `RateLimiter`) are implemented twice with slightly different logic, creating a dangerous "illusion of safety" where fixes might be applied to the wrong version.
- **Dead Code Sprawl**: Entire module trees (`prompts/`, `alerts/`) and dependencies (`websockets`) appear unused, increasing cognitive load and security surface area without adding value.
- **Version & Config Drift**: "Documentation Rot" is setting in. README claims Python 3.12+ (vs CI's 3.11) and YAML configs (vs Runtime's JSON), confusing new contributors.
- **Architecture Bottleneck**: The `async_session.py` module (~1200 lines) violates the Single Responsibility Principle, mixing orchestration, state, and execution, making it fragile to modify.

## Repo Health Scorecard

| Category | Score (0-10) | Justification |
| :--- | :---: | :--- |
| **Architecture** | **7** | Strong high-level separation, but marred by `async_session` "God Module" and duplicate resilience implementations. |
| **Code Quality** | **6** | Good typing/safety patterns, but dragged down by duplicate classes, mutable defaults in configs, and dead code. |
| **Testing** | **7** | Healthy passing suite (11/11), but lacks coverage gates or integration tests for the "Live" WebSocket path. |
| **Documentation** | **6** | Detailed but drifting. README/CI version mismatch (3.12 vs 3.11) and Config format confusion (YAML vs JSON). |
| **Deps Hygiene** | **6** | No lockfile (builds not reproducible). `websockets` unused. `requirements-dev.txt` contains tools not enforced in CI. |
| **CI / CD** | **7** | Good basics (Test/Lint/Audit), but inconsistent tooling (Pre-commit vs CI) and no formatting enforcement in CI. |
| **DX** | **6** | `la` CLI works, but internal structure (argparse inside Typer) hinders help generation. Windows `la.ps1` adds friction. |

## Findings (Prioritized)

### 1. Duplicate Circuit Breaker Implementations
- **Severity**: **Critical**
- **Why it matters**: Two competing implementations exist: `resilience/circuit.py` and `resilience/error_circuit_breaker.py`. This fragmentation risks critical safety bugs where one breaker is fixed/tested but the other (used in production) remains broken.
- **Evidence**: `resilience/circuit.py` (has `is_tripped()`) vs `resilience/error_circuit_breaker.py` (has `allow_request()`).
- **Recommendation**: consolidate on `ErrorCircuitBreaker`, deprecate the other, and update all imports.
- **Effort**: S
- **Risk**: Medium (Safety critical)
- **Verification**: `grep -r "CircuitBreaker" src` ensuring only one class is imported.

### 2. Duplicate Rate Limiter Classes
- **Severity**: **High**
- **Why it matters**: confusion between `core/rate_limiter.py` (Token Bucket, used in production) and `resilience/rate_limiter.py` (Simple, unused). Future devs may use the inferior one by mistake.
- **Evidence**: `SimpleRateLimiter` exported in `__init__.py` but not used in core logic.
- **Recommendation**: Delete `resilience/rate_limiter.py` entirely.
- **Effort**: S
- **Risk**: Low

### 3. Python Version & Config Documentation Drift
- **Severity**: **High**
- **Why it matters**: Onboarding friction. Users on 3.12 (README rec) may hit issues CI (3.11) misses. Users creating YAML configs (README rec) will fail at runtime (JSON expected).
- **Evidence**: README lines 5 vs CI workflow line 14.
- **Recommendation**: Align everything to Python 3.11 (or add 3.12 to CI matrix) and update docs to specify JSON configs.
- **Effort**: S
- **Risk**: Low

### 4. Dead Modules (`alerts/`, `prompts/`)
- **Severity**: **High**
- **Why it matters**: Code that isn't running is technical debt. It confuses navigation and review.
- **Evidence**: Zero imports found for `laptop_agents.prompts` or `laptop_agents.alerts` in the codebase.
- **Recommendation**: Delete these directories.
- **Effort**: S
- **Risk**: Low

### 5. `async_session.py` God Module (~1.2k lines)
- **Severity**: **Medium**
- **Why it matters**: This file handles too much: Event Loop, Heartbeat, Shutdown logic, PID files, and Risk checks. High coupling makes it hard to test components in isolation.
- **Evidence**: `src/laptop_agents/session/async_session.py` size and complexity.
- **Recommendation**: Refactor into `heartbeat.py`, `session_state.py`, and `execution_loop.py`.
- **Effort**: L
- **Risk**: High (Core Runtime)

### 6. Hybrid Concurrency Risk in WebSocket Client
- **Severity**: **Medium**
- **Why it matters**: `BitunixWebsocketClient` spawns a `threading.Thread` to run a *new* `asyncio` event loop. This "Loop in Thread" pattern inside an already-async app invites deadlock and signal handling issues.
- **Evidence**: `data/providers/bitunix_ws.py` line 98.
- **Recommendation**: Rewrite as a standard `asyncio.Task` running in the main loop.
- **Effort**: M
- **Risk**: Medium

### 7. Split State Persistence & Atomicity
- **Severity**: **Medium**
- **Why it matters**: State is split between JSON (`state.json`, direct write) and SQLite (atomic). Crash recovery is complex if these diverge.
- **Evidence**: `write_state` (direct) vs `StateManager` (atomic).
- **Recommendation**: Unify on `StateManager` for all persistence and enforce atomic "write-tmp-rename" pattern.
- **Effort**: M
- **Risk**: Medium

### 8. No Dependency Lockfile
- **Severity**: **Medium**
- **Why it matters**: `pip install -e .` results in non-deterministic builds.
- **Recommendation**: Adopt `uv`, `poetry`, or `pip-tools` to generate a `lock` file.
- **Effort**: S
- **Risk**: Low

### 9. CLI Argument Inconsistency (`argparse` inside `Typer`)
- **Severity**: **Medium**
- **Why it matters**: `laptop_agents/commands/session.py` manually instantiates `argparse.ArgumentParser` inside a `Typer` command. This hides flags from `--help` (which Typer autogenerates) and creates a jarring UX where `la run --help` might show different flags than expected or fail to list them at all.
- **Evidence**: `src/laptop_agents/commands/session.py` line 37: `ap = argparse.ArgumentParser(...)`.
- **Recommendation**: Port all `argparse` arguments to `Typer` options/arguments in the function signature.
- **Effort**: M
- **Risk**: Medium
- **Verification**: `la run --help` shows all options.

### 10. Mutable Default in Config Model
- **Severity**: **Medium**
- **Why it matters**: `StrategyConfig.params` uses a mutable default dictionary (`{}`). In long-running processes or tests, modifying this dictionary in one instance will bleed into others, causing non-deterministic bugs ("Heisenbugs").
- **Evidence**: `src/laptop_agents/core/config.py` line 18: `params: Dict[str, Any] = {}`.
- **Recommendation**: Use `pydantic.Field(default_factory=dict)`.
- **Effort**: S
- **Risk**: Low
- **Verification**: `grep "params: Dict.*= {}" src/laptop_agents/core/config.py` should return nothing.

### 11. Scripts Directory Sprawl
- **Severity**: **Low**
- **Why it matters**: `scripts/` contains 26 files with unclear ownership, including superseded versions (`optimize_strategy.py` vs `_v2.py`) and one-off diagnostics (`monte_carlo_v1.py`). This adds cognitive load and maintenance burden.
- **Evidence**: `ls scripts/` shows 26 files including versioned duplicates.
- **Recommendation**: Archive unused scripts to a `scripts/archive/` folder and identify canonical tools in `scripts/README.md`.
- **Effort**: S
- **Risk**: Low

### 12. Dev Dependency Misalignment
- **Severity**: **Low**
- **Why it matters**: `requirements-dev.txt` lists tools (`pytest-cov`, `pytest-xdist`, `autoflake`) that are not enforced or used in the CI workflow, creating a gap between local dev experience and CI verification.
- **Evidence**: `requirements-dev.txt` vs `.github/workflows/ci.yml`.
- **Recommendation**: Align sources of truth: either add these tools to CI or remove them if unused.
- **Effort**: S
- **Risk**: Low

### 13. Duplicate HTTP Libraries (`httpx` vs `aiohttp`)
- **Severity**: **Low**
- **Why it matters**: The codebase uses `httpx` for REST calls (Bitunix Futures, Logging) and `aiohttp` for WebSockets (Bitunix WS). Maintaining two async HTTP clients increases binary size and dependency surface area.
- **Evidence**: `import httpx` in `bitunix_futures.py` vs `import aiohttp` in `bitunix_ws.py`.
- **Recommendation**: Standardize on `httpx`, which now supports WebSocket connections natively (since v0.20+), removing `aiohttp` entirely.
- **Effort**: M
- **Risk**: Low
- **Verification**: `grep "import aiohttp" src` should return nothing.

### 14. Artifacts Committed to Repo
- **Severity**: **Low**
- **Why it matters**: `test_state_broker.db` and other test artifacts are present in the root directory. Committing binary state files bloats history and risks leaking local state.
- **Evidence**: file exists in root.
- **Recommendation**: Remove from repo and add `*.db` and `testall-report.*` to `.gitignore`.
- **Effort**: S
- **Risk**: Low

### 15. Tooling & Linter Fragmentation
- **Severity**: **Low**
- **Why it matters**: Local `pre-commit` hooks use `black` and `flake8`, while CI runs `mypy` and `pip-audit`. This creates a disjointed loop where code passes local checks but fails in CI (or vice-versa), frustrating contributors.
- **Evidence**: `.pre-commit-config.yaml` uses legacy formatters; CI lacks formatting checks.
- **Recommendation**: Unify on `ruff` for both formatting and linting. Ensure CI runs the exact same command (`la doctor --lint`) as local development.
- **Effort**: S
- **Risk**: Low

## Removals & Simplifications

| Candidate | Reason | Safe to Remove? |
| :--- | :--- | :--- |
| `src/laptop_agents/prompts/` | Dead code (0 imports). | **YES** |
| `src/laptop_agents/alerts/` | Dead code (0 imports). | **YES** |
| `resilience/rate_limiter.py` | Duplicate of `core` rate limiter. | **YES** |
| `resilience/circuit.py` | Duplicate/Inferior to `error_circuit_breaker`. | Verify `TradingCircuitBreaker` usage first. |
| `websockets` (dependency) | Code uses `aiohttp` for WS. | **YES** (Verify no dynamic imports). |
| `la.ps1` | Redundant if `pip` entry points used. | **YES** (Docs update needed). |

## Maintainability Roadmap

### Immediate (0-2 Weeks)
- [ ] **Purge Dead Code**: Delete `alerts/`, `prompts/`, and unused `resilience` duplicates.
- [ ] **Fix Doc Drift**: Update README to match CI (Python 3.11, JSON Configs).
- [ ] **Dep Hygiene**: Remove `websockets` dependency and generate a lockfile.
- [ ] **Cleanup Scripts**: Archive unused scripts in `scripts/` and consolidate dev dependencies.
- [ ] **Git Hygiene**: Add `*.db` to `.gitignore` and remove `test_state_broker.db`.
- [ ] **Tooling Match**: Align local pre-commit with CI (adopt `ruff` everywhere).

### Structural (1-2 Months)
- [ ] **Unify Resilience**: Consolidate all Rate Limiters/Circuit Breakers into `core/resilience` with single sources of truth.
- [ ] **Refactor God Module**: Break down `async_session.py` into distinct components.
- [ ] **CLI Polish**: Refactor `session.py` to use `Typer` arguments directly (removing `argparse`).
- [ ] **Consolidate HTTP**: Replace `aiohttp` with `httpx` for WebSockets to drop one dependency.

### Strategic (3-6 Months)
- [ ] **Concurrency Model**: Move WebSocket client to pure `asyncio` (remove threading).
- [ ] **Unified Persistence**: Move all state to a single SQLite DB or atomic JSON store with strict schema validation.
- [ ] **Quality Gates**: Add coverage thresholds and strict type checking to CI.

## Quality Gates (Future-Proofing)

1.  **Format & Lint**: Enforce `ruff format --check` and `ruff check` in CI. Fail on any violation.
2.  **Strict Typing**: Pin `mypy` version and increment strictness (e.g., `disallow_untyped_defs`) on core modules.
3.  **Dependency Lock**: Fail CI if `uv.lock` or `requirements.lock` is out of sync with `pyproject.toml`.
4.  **Reliability Smoke Test**: Run a minimal `la run --mode backtest --dry-run` in CI to verify CLI entry point and core import paths.
5.  **Duplication**: Enforce zero tolerance for new code duplication using `pylint` or `sonarqube`.
