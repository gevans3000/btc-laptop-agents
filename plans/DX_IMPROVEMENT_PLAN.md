# Developer Experience & Autonomy Improvement Plan

This plan consolidates feedback to improve the Developer Experience (DX) and Autonomy of the `btc-laptop-agents` system. It solves issues related to fragmented entry points, lack of version control visibility, and manual operational overhead.

## Phase 1: Immediate Polish (Quick Wins)
**Goal:** Improve visibility, consistency, and basic operational control without major refactoring.

### 1.1 Unify Versioning & Add Identity
- [ ] **Fix Version Mismatch**: Update `src/laptop_agents/__init__.py` to match `pyproject.toml` (`1.0.1`).
- [ ] **Add `--version` Flag**: logic in `src/laptop_agents/run.py` (and eventually the unified CLI) to print version and exit.
- [ ] **Add Startup Banner**: Print a `rich` formatted banner at startup showing version, mode, symbol, strategy, and source.

### 1.2 Enhanced CLI Control
- [ ] **Add `--quiet` / `--verbose` Flags**:
    - `quiet`: Set log level to ERROR, suppress stdout print statements.
    - `verbose`: Set log level to DEBUG.
- [ ] **Environment Variable Defaults**: Ensure all critical `run.py` args (`--symbol`, `--duration`, `--strategy`, `--source`) default to values from `os.environ` (e.g., `LA_SYMBOL`) if not provided via flags.

### 1.3 Post-Run Validation
- [ ] **Explicit Exit Codes**: Modify `run.py` to check for essential artifacts (`summary.html`, `events.jsonl`) before returning `0`. If missing, return `1`.
- [ ] **Status Report**: Print a concise "Session Summary" to stdout at the end of a run (Duration, Trades, PnL, Artifacts location).

## Phase 2: Unification & Tooling (Medium Effort)
**Goal:** Consolidate multiple entry points and provide robust maintenance tools.

### 2.1 Unified CLI (`la`)
Refactor the distinct `run.py` (argparse) and `cli.py` (typer) into a single Typer application.
- [ ] **Create `src/laptop_agents/main.py`**: A new Typer app that serves as the single entry point.
- [ ] **Migrate `run.py` logic**: Move the `run` command to be a subcommand: `la run`.
- [ ] **Migrate `cli.py` commands**: Move `debug-feeds`, `replay`, etc., as subcommands: `la debug-feeds`, `la replay`.
- [ ] **Update `pyproject.toml`**: Point `project.scripts.la` to `laptop_agents.main:app`.

### 2.2 Operational Commands
- [ ] **Implement `clean` command**: `la clean --days 7`. Deletes old run directories safely.
- [ ] **Implement `status` command**: `la status`. Checks PID file, prints if running, duration, and last heartbeat.

### 2.3 Robust Process Management
- [ ] **Centralized Lock Manager**: Create `src/laptop_agents/core/lock_manager.py`.
    - Unified logic for acquiring/releasing locks.
    - Check for stale PIDs (process no longer exists).
    - Use this in `la run` and `la status`.

## Phase 3: Architecture & Safety (High Reliability)
**Goal:** Make the system self-validating and configuration-safe.

### 3.1 Declarative Configuration
- [ ] **Pydantic Config Models**: Create `src/laptop_agents/core/config.py`.
    - Define models for `SessionConfig`, `RiskConfig`, `StrategyConfig`.
    - Implement `load_config` that validates JSON/Env-vars against these models.
    - Replace ad-hoc dictionary lookups in `run.py`/`main.py`.

### 3.2 Self-Validating Run Result
- [ ] **`RunResult` Schema**: Return a structured object from run functions instead of just `int` or `bool`.
    - Fields: `success: bool`, `exit_code: int`, `validation_errors: list[str]`, `artifacts: dict`.
- [ ] **Automated Validation**: The orchestration layer checks `RunResult` and fails the process if the run claimed success but artifacts are missing.

## Phase 4: Extras (The "Extra Mile")
**Goal:** Add pro-active health and developer convenience features.

### 4.1 Health Check (`la doctor`)
- [ ] **Implement `la doctor`**:
    - Verify Python version.
    - Check `.env` exists and has required keys (e.g., API keys if mode=live).
    - Check directory write permissions (`runs/`, `logs/`, `data/`).
    - Verify accurate time sync (warn if system clock drift > 1s vs NTP/API).

### 4.2 Git Hooks Integration
- [ ] **Version Sync Hook**: A pre-commit hook that ensures `pyproject.toml` and `__init__.py` versions match.

### 4.3 Log Management
- [ ] **Log Rotation**: Configure `logger.py` to use `RotatingFileHandler` (max 10MB, keep 5 backups) to prevent disk fill-up on long-running instances.

## Execution Order
1.  **Phase 1** (Can be done in one session, high impact).
2.  **Phase 2** (Consolidates the codebase, reduces confusion).
3.  **Phase 3** (Hardens the system against bad config/state).
4.  **Phase 4** (Nice to have).

This plan is ready for autonomous execution.
