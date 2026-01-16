# PROMPT: Execute Top 5 DX & Maintainability Wins

You are an expert Devex Engineer. Your goal is to autonomously execute the "Top 5 Wins" from the recent codebase audit. 

These tasks address critical blockers, dual entrypoints, logging fragmentation, type safety, and script hygiene.

**Constraints:**
-   **Autonomy**: Do not ask for permission. If a step fails, attempt to fix it once, then proceed or report if blocking.
-   **Idempotency**: All run commands and file edits must be safe to run multiple times.
-   **Verification**: Run a quick verification check after each phase.

---

## **Phase 1: Fix Dependencies [BLOCKER]**
**Goal**: Create the missing `requirements.txt` so Docker builds work.

1.  **Analyze** `pyproject.toml` to identify dependencies.
2.  **Create** `requirements.txt` in the root directory.
    -   Include all runtime dependencies: `python-dotenv`, `pydantic`, `rich`, `typer`, `httpx`, `psutil`.
    -   Add versions if present in pyproject.toml (e.g., `>=1.0.1`).
3.  **Verify**: Log "Checked requirements.txt" if file exists.

---

## **Phase 2: Unify CLI Entrypoints [HIGH]**
**Goal**: Remove the legacy `cli.py` and consolidate commands into the new `main.py` structure.

1.  **create** `src/laptop_agents/commands/legacy.py`.
    -   Copy all contents from `src/laptop_agents/cli.py` into this new file.
    -   Ensure imports in the new file are correct relative to its location.
2.  **Refactor** `src/laptop_agents/main.py`.
    -   Change `from laptop_agents import cli as old_cli` to `from laptop_agents.commands import legacy as old_cli`.
    -   Ensure all `app.command` registrations for legacy commands (`debug-feeds`, `run-mock`, `replay`, `report`, `journal-tail`) start referencing `old_cli` functions correctly.
3.  **Delete** `src/laptop_agents/cli.py`.
4.  **Verify**: Run `la --help` (or `python -m laptop_agents.main --help`) to ensure commands are listed without error.

---

## **Phase 3: Centralize Logging [HIGH]**
**Goal**: Enforce use of `core.logger` and remove fragmentation.

1.  **Delete** `src/laptop_agents/core/logging.py` (it is redundant/confusing).
2.  **Search & Replace**: Find all files in `src/` that strictly contain `import logging` (excluding `src/laptop_agents/core/logger.py`).
    -   *Targets likely include*: `paper/broker.py`, `execution/bitunix_broker.py`, `core/runner.py`, `core/rate_limiter.py`, `commands/session.py`, `backtest/engine.py`.
    -   **Action**:
        -   Remove `import logging`.
        -   Remove `logger = logging.getLogger(__name__)` if present.
        -   Add `from laptop_agents.core.logger import logger`.
3.  **Verify**: Run `grep -r "import logging" src/laptop_agents` to ensure only `core/logger.py` remains.

---

## **Phase 4: Enable Type Checking [HIGH]**
**Goal**: Establish infrastructure for static analysis.

1.  **Update** `pyproject.toml`:
    -   Add a `[tool.mypy]` section.
    -   Settings:
        ```toml
        [tool.mypy]
        python_version = "3.10"
        ignore_missing_imports = true
        check_untyped_defs = true
        ```
2.  **Verify**: Run `mypy src/ --no-error-summary` (just to confirm the tool runs; ignore the actual type errors for now).

---

## **Phase 5: Cleanup Scripts [MEDIUM]**
**Goal**: Organize the `scripts/` directory.

1.  **Delete** `scripts/supervisor.py` (It is a duplicate of the `la watch` command).
2.  **Move** Tests:
    -   Create directory `tests/manual`.
    -   Move `scripts/test_*.py` files into `tests/manual/`.
3.  **Create** `scripts/README.md`:
    -   Audit the remaining scripts in `scripts/`.
    -   Write a simple markdown table listing them and their apparent purpose (e.g., `check_*.py` for validation, `diagnose_*.py` for debugging).
4.  **Verify**: List `scripts/` content to confirm cleanup.

---

**Final Output**:
When finished, print a summary checklist of completed phases.
