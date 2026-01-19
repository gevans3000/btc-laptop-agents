# Autonomous Workflow Upgrade Plan

**Objective**: Enhance the developer experience by upgrading `.agent/workflows` to include auto-formatting, parallel testing, advanced monitoring, and automated cleanup.

**Instructions for the Agent**:
Read this entire plan. Analyze the existing workflows in `.agent/workflows/`. Execute the implementation steps below. Verify all changes.

## 1. Prerequisites (Dependency Management)
- [x] Install/Verify the following Python packages are added to `requirements.txt` (or dev dependencies) and installed in the environment:
    - `black` (for code formatting)
    - `autoflake` (for cleaning imports)
    - `pytest-xdist` (for parallel testing)
    - `psutil` (for system monitoring)

## 2. Create the `/clean` Workflow
**File**: `.agent/workflows/clean.md`
**Goal**: Safely prune artifacts to prevent disk bloat.
**Steps**:
- [x] Create `.agent/workflows/clean.md` with the following steps:
    1.  **Clean Python Cache**: Remove `__pycache__` and `.pytest_cache` directories recursively.
    2.  **Prune Logs**:
        -   Keep only the last 5 `system.jsonl` files (if logs are rotated).
        -   Maintain the main `logs/system.jsonl` but warn if it exceeds 50MB.
    3.  **Clean Temp Artifacts**: Remove contents of `pytest_temp/` and old HTML reports in `paper/` (> 7 days old).

## 3. Upgrade the `/go` Workflow
**File**: `.agent/workflows/go.md`
**Goal**: "Zero-Chore" commits with auto-formatting and fast feedback.
**Steps**:
- [x] **Inject Formatting Step**: Before "Syntax Check", add a "Code Formatting" step:
    -   Run `autoflake --in-place --remove-all-unused-imports --recursive src tests`
    -   Run `black src tests`
    -   (Note: Use `// turbo` for this step to auto-run it).
- [x] **Parallel Tests**: Update the "Unit Tests" step:
    -   Change `pytest` command to use `-n auto` (requires `pytest-xdist`).
- [x] **Improve Commit Logic**: Update the "Generate Commit Message" step to be more granular:
    -   Use `git diff --cached --name-only` to identify modified scopes.
    -   Construct the message variables `$commitType` and `$scope` intelligently.

## 4. Upgrade the `/status` Workflow
**File**: `.agent/workflows/status.md`
**Goal**: Deeper observability.
**Steps**:
- [x] **Disk Usage**: Add a PowerShell step to calculate and display the size of `.workspace/` and `logs/`. Warn if total > 500MB.
- [x] **Memory Usage**: Add a step (inline Python or PowerShell) to check the current system memory usage or process memory.
- [x] **Connectivity**: Add a step to ping `www.google.com` (for internet) and `api.bitunix.com` (for exchange) to verify latency.

## 5. Verification
- [x] Run the `/clean` workflow commands manually to verify they remove artifacts.
- [x] Run the updated `/go` commands manually to ensure `black` formats code and `pytest -n auto` works properly.
- [x] Run the `/status` commands manually to verify new metrics appear correctly in the output.
