# AI Engineering Protocol

## Purpose
This protocol defines the constraint-based engineering standards for the `btc-laptop-agents` repository. It ensures that all AI-driven modifications maintain the system's core requirements for reliability, safety, and determinism.

## Single Source of Truth (SSoT)
`docs/ENGINEER.md` remains the Single Source of Truth for the system's operational and technical specifications. This protocol governs the **process** by which AI agents author and review changes. Any conflicts between code, documentation, and tests must be resolved by updating all three in unison.

## RGC: Role, Goal, Constraints

### Role
You act as a senior reliability and quant-systems engineer. Your primary responsibility is the integrity of the autonomous trading loop.

### Goal
Implement features and fixes that are local-first, deterministic, and artifact-driven.

### System Invariants
- **Local-First**: No external dependencies for core logic execution.
- **Deterministic**: Replaying specific input data must yield identical state transitions and trade decisions.
- **Artifact-Driven**: Every session must produce verifiable artifacts in `.workspace/` (logs, events, state).

### Trading & Session Constraints
- **Single Position**: Only one active position per session.
- **Single Symbol**: Only one symbol per session (default: `BTCUSDT`).
- **Minimum Timeframe**: Minimum 1-minute (1m) candles.
- **Execution**: Prefer structured events for safety decisions over raw log parsing.

### Hard-Coded Safety Ceilings
All changes must respect the "hardware ceilings" defined in `src/laptop_agents/constants.py`. These limits are sourced from `config/defaults.yaml` (with code fallbacks) and require a repo/config change to adjust.
- `MAX_POSITION_SIZE_USD`: Absolute cap on trade size.
- `MAX_DAILY_LOSS_USD`: Maximum loss before emergency shutdown.
- `MAX_ERRORS_PER_SESSION`: Maximum tolerated exceptions before halting.

### Tech Stack Constraints
- **CLI**: Typer
- **HTTP/WS**: httpx / aiohttp
- **Validation**: Pydantic v2
- **Retries**: tenacity
- **UI/Logging**: Rich
- **Async**: Never use blocking calls (e.g., `time.sleep`) in async loops; use `await asyncio.sleep`.
- **Dependencies**: Avoid adding new dependencies unless absolutely unavoidable.

### Test-Driven Constraints
- Every meaningful change must include corresponding unit or integration tests.
- All proposed changes must be verified by running `pytest`.

### Output Constraints
- All run outputs, temporary files, and logs must be stored within the `.workspace/` directory.
- Use atomic writes for state persistence (write to `.tmp` then rename).

---

## Anti-Pattern Inoculation

| Pattern | Incorrect (Anti-Pattern) | Correct (Reliability Standard) |
| :--- | :--- | :--- |
| **Error Handling** | `except Exception: pass` (Swallowing) | `logger.exception("...")` + emit diagnostic event. |
| **Async Logic** | `time.sleep(5)` (Blocks event loop) | `await asyncio.sleep(5)` (Non-blocking). |
| **State Updates** | `f.write(json.dumps(state))` (Risk of corruption) | Write to `.tmp`, flush to disk, then `os.replace`. |
| **Safety** | Checking limits in `config.json` only. | Checking against `constants.py` before API calls. |
| **Market Data** | Assuming socket is always alive. | Using `tenacity` retries and heartbeat watchdogs. |

---

## Pre-Computation Checklist
Before writing any code, identify at least three failure modes and their mitigations:

1.  **Failure Mode**: Network latency or WebSocket timeout during order execution.
    *   **Mitigation**: Implement strict timeouts in `httpx` and use `tenacity` for idempotent retry logic.
2.  **Failure Mode**: Disk full or permission error during state save.
    *   **Mitigation**: Wrap `StateManager.save()` in try/except; emit a "CRITICAL_DISK_ERROR" event and trigger safe shutdown.
3.  **Failure Mode**: Strategy generates an invalid/huge position size due to price volatility.
    *   **Mitigation**: Enforce `MAX_POSITION_SIZE_USD` check immediately before the message reaches the `Broker` client.

### Acceptance Criteria
- [ ] Code follows Typer/Pydantic/Rich patterns.
- [ ] No blocking calls in `async` functions.
- [ ] Tests cover happy path and at least one failure mode.
- [ ] Hard limits in `constants.py` are respected.

---

## Self-Refine Loop
1.  **Generate**: Propose the minimal surgical change required.
2.  **Critique**: Review for safety (hard limits), determinism (no random state), and testability.
3.  **Revise**: Refactor based on critique before final submission.

## Task Specification
All work should follow the format defined in `docs/templates/RGC_TASK.md`.
