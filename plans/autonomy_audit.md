# Autonomy & Systems Audit

**Date:** 2026-01-16
**Scope:** `src.laptop_agents`, `scripts/`, `config/`
**Auditor:** Antigravity (Senior Reviewer)

## 1. Executive Summary

The current system relies on a **"Script-Wrapped" Architecture**. The core Python application is robust and capable, but the user interface relies heavily on fragile PowerShell wrappers (`mvp_*.ps1`) that hardcode arguments and lack true process supervision.

While the system is "autonomous" in the sense that it can run in the background, it lacks **Active Autonomy** (self-healing, self-validating on start) and **Unified Configuration** (users must juggle CLI args, JSON configs, and script hardcoding).

**Verdict:** Functional but fragile. High friction for "power users" and insufficient feedback for "new users" when things go silently wrong.

## 2. Deep Dive Diagnosis

### A. Autonomy (Grade: C+)
*   **Strengths:**
    *   PID locking prevents double runs.
    *   `atexit` handlers ensure cleanups on normal exits.
    *   `AsyncRunner` (internal) likely handles retry logic for networking.
*   **Weaknesses:**
    *   **No Supervision:** If the Python process crashes (segfault, OOM, unhandled exception), `mvp_start_live.ps1` just leaves a stale PID file. There is no supervisor loop to restart it.
    *   **Silent Failures:** The "Heartbeat" is a file timestamp. If the process hangs (deadlock), the PID exists, so `mvp_status.ps1` says "RUNNING", but no trading is happening.
    *   **Validation Gaps:** `mvp_start_live.ps1` hardcodes `--source mock`. If a user wants `live` data, they must edit the script or use the raw CLI, losing the "MVP" safety net.

### B. Ease of Management (Grade: B-)
*   **Strengths:**
    *   Documentation (`README.md`) is excellent and task-oriented.
    *   `mvp_open.ps1` is a nice touch for immediate value.
    *   `logs/system.jsonl` provides structured data.
*   **Weaknesses:**
    *   **Config Split-Brain:** Configuration is scattered across `config/default.json`, `src/laptop_agents/run.py` (argparse defaults), and `scripts/mvp_start_live.ps1` (hardcoded args).
    *   **Validation False Positives:** `validation.py` enforces `BITUNIX_API_KEY` presence for `mode="live"`, even if `--source mock` is used. This causes confusion for paper-trading users.
    *   **Opaque Startup:** When started, the logs don't clearly dump the *effective* configuration. A user is left guessing: "Did it load my strategy? Is it using the right risk %?".

## 3. Prioritized Improvements

### Phase 1: Quick Wins (Confidence & Cleanup) - COMPLETED
*   **[x] Fix 1.1: Context-Aware Validation**
    *   **Fix:** Only validate API keys if `--source bitunix`. (Implemented in `validation.py`)
*   **[x] Fix 1.2: Effective Config Dump**
    *   **Fix:** In `run.py`, immediately after config usage, log a `SYSTEM_STARTUP` event containing the merged JSON config. (Implemented in `run.py`, also set default source to `mock`).
*   **[x] Fix 1.3: Enhanced Status Script**
    *   **Fix:** Check the modification time of `logs/heartbeat.json`. If > 60s old, report **ZOMBIE / HUNG**. (Implemented in `mvp_status.ps1`).

### Phase 2: Medium Effort (Configuration Unification) - COMPLETED
*   **[x] Fix 2.1: "Config First" Architecture**
    *   **Fix:** Deprecate most CLI args in favor of `--config <path>`. Make `run.py` load config first and treat CLI args as explicit overrides. (Implemented in `run.py`).
*   **[x] Fix 2.2: Script Profiles**
    *   **Fix:** Add a parameter: `mvp_start_live.ps1 -Profile <name>`. (Implemented in `mvp_start_live.ps1`).
        *   Example usage: `.\scripts\mvp_start_live.ps1 -Profile scalp_1m_sweep -Symbol BTCUSDT`

### Phase 3: Architectural Upgrades (True Autonomy)
*   **Fix 3.1: Python-Based Supervisor**
    *   **Issue:** PowerShell is a poor process supervisor.
    *   **Fix:** Create `src/laptop_agents/supervisor.py`.
        *   It launches the runner as a subprocess.
        *   It monitors the return code.
        *   If crash -> restarts (up to N times).
        *   If clean exit -> stops.
        *   `mvp_start_live.ps1` launches the *Supervisor*, not the Runner.
*   **Fix 3.2: Self-Healing State**
    *   **Issue:** Corrupt state files stop the bot.
    *   **Fix:** startup routine should valid `state.json`. If corrupt, mv to `state.bak` and start fresh (or from last checkpoint), logging a critical warning.

## 4. Implementation Plan (Next Steps)

1.  **Immediate:** Apply Fix 1.1 (Validation) and Fix 1.2 (Config Dump) to reduce user debugging friction.
2.  **Next:** Update `mvp_status.ps1` to be "Smart" (Heartbeat aware).
3.  **Strategic:** Refactor `run.py` to prioritize `config.json` loading over CLI defaults.
