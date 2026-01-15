# Learning Debugger Integration Plan

This plan integrates the "Learning Debugger" system (error fingerprinter, solution database, and learned lint rules) into the core development lifecycle steps: Testing, Runtime, Committing, and Documentation.

## Phase 1: Test Suite Integration ("Just-in-Time Diagnostics")
**Goal**: When tests fail, immediately suggest known solutions and queue unknown errors for diagnosis.

### 1.1 Update `tests/conftest.py`
- Implement a `pytest_exception_interact` hook.
- **Logic**:
  1. Capture the exception and traceback.
  2. Call `scripts/error_fingerprinter.py match` (import the logic directly if possible to avoid subprocess overhead).
  3. If a match is found:
     - Print `MATCHED KNOWN ERROR: <Name>`
     - Print `SUGGESTED FIX: <Solution>`
  4. If no match is found:
     - Serialize the error to `pending_errors.json` (using `scripts/diagnose_pending_errors.py` logic) so the `/debug` workflow sees it later.

## Phase 2: Runtime Exception Handling ("Crash Advisory")
**Goal**: When the live application crashes, look up the error in the knowledge base before exiting.

### 2.1 Update `src/laptop_agents/core/orchestrator.py` (or main entry point)
- Wrap the main execution loop in a global `try/except` block.
- **Logic**:
  1. Catch generic `Exception`.
  2. Before logging the stack trace, consult `error_fingerprinter.py`.
  3. Log the "Known Solution" if one exists alongside the standard error log.
  4. Ensure `pending_errors.json` is updated with this new crash instance.

## Phase 3: Pre-Commit Regression Firewall
**Goal**: Prevent known buggy code patterns from entering the codebase.

### 3.1 Update `.agent/workflows/pre-commit.md`
- Add a mandatory step to run `scripts/check_lint_rules.py`.
- **Constraint**: This step must fail the workflow if *any* learned lint rules are violated.
- **Instruction**: Ensure the command is:
  ```powershell
  python scripts/check_lint_rules.py
  ```

## Phase 4: Automated Knowledge Base ("Dynamic Troubleshooting")
**Goal**: Convert the JSON error database into human-readable documentation.

### 4.1 Create `scripts/generate_troubleshooting_docs.py`
- **Function**: Reads `error_fingerprints.json` (or the `learned_errors` directory).
- **Output**: Generates `docs/troubleshooting/known_issues.md`.
- **Format**:
  - **Header**: "Automated Troubleshooting Guide"
  - **Table of Contents**
  - **Section per Error**:
    - **Title**: Error Name/Fingerprint
    - **Description**: What happens.
    - **Root Cause**: Why it happens.
    - **Solution**: How to fix it.

### 4.2 Update `.agent/workflows/sync-docs.md`
- Add a step to run `python scripts/generate_troubleshooting_docs.py` before the final commit/push.

## Verification
1. **Test Hook**: Run a test known to fail. Verify console output shows "SUGGESTED FIX" or updates `pending_errors.json`.
2. **Runtime**: Intentionally crash the orchestrator. Verify logs show the advisory.
3. **Pre-Commit**: Insert a known "bad pattern" (that triggers a learned lint rule) and run `/pre-commit`. It should fail.
4. **Docs**: Run `/sync-docs` and verify `docs/troubleshooting/known_issues.md` is created and populated.
