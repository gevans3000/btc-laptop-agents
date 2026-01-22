# AUDIT_NOTES

## Repo Map

### Entry Points
- CLI: `la` (maps to `laptop_agents.main:app`)
- Module: `python -m laptop_agents` (see `src/laptop_agents/__main__.py`)

### Main Modules (src/laptop_agents)
- `agents/`: agent orchestration
- `alerts/`: alerting hooks
- `backtest/`: backtesting engine
- `commands/`: CLI subcommands
- `core/`: event bus and core utilities
- `dashboard/`: dashboard rendering
- `data/`: market data providers
- `execution/`: order routing and execution logic
- `memory/`: local memory/state handling
- `paper/`: paper trading simulation
- `reporting/`: reports and summaries
- `resilience/`: retry, circuit breaker, and safety
- `session/`: session orchestration
- `storage/`: persistence and artifact helpers
- `trading/`: trading models and helpers
- `main.py`: CLI app bootstrap
- `constants.py`, `health.py`, `indicators.py`: shared utilities

### Key Commands
- Install: `pip install -e .[test]`
- Doctor: `python -m laptop_agents doctor --fix`
- Run mock session: `python -m laptop_agents run --mode live-session --duration 1 --source mock --async`
- Build: `python -m build`
- Compile: `python -m compileall src scripts -q`
- Tests: `pytest -q --tb=short`
- Types: `python -m mypy src/laptop_agents --ignore-missing-imports --no-error-summary`
- Security: `pip-audit`

## Baseline Failures
- `python -m pip install -e .[test]` failed: permission denied creating temp pip build tracker directory.
- `python -m laptop_agents doctor --fix` crashed with `UnicodeEncodeError` when printing a checkmark to a cp1252 console.
- `pwsh ./scripts/codex_review.ps1` failed: `pwsh` not found.
- `.\scripts\codex_review.ps1` failed: PowerShell execution policy blocks script execution.
- `python -m build` failed: missing `build` module.
- `pytest -q --tb=short` failed: `pytest` not found on PATH.
- `pip-audit` failed: `pip-audit` not found on PATH.
