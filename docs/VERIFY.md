# VERIFY.md â€” Verification Protocol

> **STATUS**: ACTIVE
> **PURPOSE**: Define what "Green" means.

## 1. The Verify Script
`verify.ps1` is the supreme judge of repo health.

### Levels
*   **Quick**: `verify.ps1 -Mode quick` (< 10s).
    *   Compilation check.
    *   Unit tests (if any).
    *   Risk Engine Self-Test (Logic check).
*   **Full**: `verify.ps1 -Mode full` (< 2m).
    *   All Quick checks.
    *   Short Backtest (sanity check).
    *   Validation Grid run (integration check).

## 2. Self-Test Standard
The `selftest` mode in `run.py` is the core of our safety. It does NOT use random data. It uses a **deterministic sine wave**.

**Required Scenarios (Must Pass):**
1.  **Long Win**: Entry -> Target Hit -> Exit.
2.  **Long Loss**: Entry -> Stop Hit -> Exit.
3.  **Short Win**: Entry -> Target Hit -> Exit.
4.  **Short Loss**: Entry -> Stop Hit -> Exit.
5.  **Reversal**: Long Entry -> Signal Flip -> Close & Reverse.

## 3. Operations Verification
How to verify the live system:
1.  **Start**: PID file appears.
2.  **Heartbeat**: `events.jsonl` updates every interval.
3.  **State**: `state.json` updates balance on trade close.
4.  **Recovery**: Killing pid and restarting resumes safely.

