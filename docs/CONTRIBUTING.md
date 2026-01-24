# Contributing to BTC Laptop Agents

## 1. Philosophy
We treat this repository as a high-reliability financial system. Code is not just "merged"; it is verified, hardened, and proven safe.

### The AI Engineering Protocol
All changes must strictly adhere to the [AI Engineering Protocol](AI_ENGINEERING_PROTOCOL.md).
Key rules:
1. **Local-First**: No external dependencies for core logic.
2. **Deterministic**: Same input + Same seed = Same result.
3. **Artifact-Driven**: If it didn't log to `.workspace/`, it didn't happen.

---

## 2. Development Setup

### Install
```powershell
# Install development environment (including test dependencies)
pip install -e .[test]
# Verify
la doctor
```

---

## 3. Standard Workflows

We use `make` or script aliases for common loops.

### A. Review (Read-Only)
Use when you want a read-only review report plus basic checks.
```powershell
.\scripts\codex_review.ps1
# OR
make review
```

### B. Auto-Fix
Use when tests fail and you want a safe loop that can call Codex to fix and re-run.
```powershell
.\scripts\codex_fix_loop.ps1
# OR
make fix
```

### C. Pre-PR Hardening
Use before opening a PR or sharing changes.
```powershell
python -m mypy src/laptop_agents --ignore-missing-imports --no-error-summary
python -m pytest tests/ -q --tb=short
# OR
make harden
```

### D. Formatting (Required)
Keep code formatted to avoid CI failures.
```powershell
python -m ruff format src tests
python -m ruff check src tests --fix
```
### E. Agent "Go" Workflow (Recommended)
The fastest way to verify, commit, and ship changes autonomously.
```powershell
# In the Agent Chat
/go
```
This runs `testall.ps1`, formats code, and commits with a semantic message.

---

## 4. Testing Strategy

We use a tiered testing approach.

### Tier 1: Smoke Test
Quickly verify the system boots and connects.
```powershell
la doctor --fix
la run --mode live-session --duration 1 --source mock --dry-run
```

### Tier 2: Core Tests
```powershell
pytest tests/
```

### Tier 3: Full System Matrix (`testall`)
Runs stability loops and environment checks.
```powershell
.\testall.ps1 -Fast       # 1-minute stability check
.\testall.ps1             # 5-minute stability check
```
*Note: `testall.ps1` generates AI-friendly JSON reports in `._testall_artifacts/`.*

---

## 5. Review Guidelines

When reviewing code (AI or Human), strict criteria apply:

- **Correctness**: Behavior must match intent and existing contracts.
- **Security**: No leaked secrets, valid inputs only.
- **Performance**: No blocking calls in `async` functions (use `await asyncio.sleep`).
- **Edge Cases**: Must handle timeouts, empty data, and network failures.
- **Persistence**: State must be saved atomically (write to temp -> rename).

---

## 6. Documentation Protocol

To prevent drift, we follow these rules:

1.  **Single Source of Truth**:
    -   `README.md`: Index & Quick Links.
    -   `ENGINEER.md`: Operational Manual & System Specs.
    -   `CONTRIBUTING.md`: Dev Process (this file).

2.  **Maintenance**:
    -   Do not create loose `.md` files in the root (move audit artifacts into `docs/archive/`).
    -   One workflow = One authoritative document.
    -   Delete documentation aggressively when its purpose is served (e.g., implementation plans).

3.  **Changes**:
    -   If you change the CLI, update `ENGINEER.md`.
    -   If you change the Architecture, update `ENGINEER.md`.
    -   If you change the Testing process, update `CONTRIBUTING.md`.
