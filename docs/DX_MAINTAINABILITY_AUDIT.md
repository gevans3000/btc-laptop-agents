# DX & Maintainability Audit — BTC Laptop Agents

> **Auditor**: AI Audit System
> **Date**: 2026-01-16
> **Repository**: https://github.com/gevans3000/btc-laptop-agents
> **Version Audited**: 1.1.0 (Structural Polish Phase 3)

---

## 1. Executive Summary

### Top DX/Maintainability Wins (Priority Order)

1. **🔴 BLOCKER: Test Suite Broken** — `conftest.py` uses Unicode characters (✓) that fail on Windows cp1252 encoding, causing `INTERNALERROR` and preventing all tests from running. Zero tests can pass in CI or locally on Windows.

2. **🔴 HIGH: 60+ mypy Type Errors** — Critical type safety issues including `Optional` type violations, incompatible assignments, undefined attributes, and incorrect function signatures. This creates runtime risk and makes refactoring dangerous.

3. **🟠 HIGH: Duplicate Rate Limiter Implementations** — Two separate `rate_limiter.py` files exist (`core/rate_limiter.py` and `resilience/rate_limiter.py`). Also `config.py` and `config_models.py` have overlapping responsibilities.

4. **🟠 HIGH: Missing `requirements.txt`** — Dockerfile references `requirements.txt` which doesn't exist. Docker builds will fail immediately.

5. **🟡 MEDIUM: Pydantic v1 Deprecated API** — `config.py:75` uses `__fields__` attribute which is deprecated in Pydantic v2 (mypy error confirms this). Breaks with future Pydantic updates.

6. **🟡 MEDIUM: Hardcoded Paths & Magic Numbers** — Multiple files use hardcoded paths like `"paper/last_price_cache.json"` instead of referencing `REPO_ROOT`. Magic numbers like `1500` MB memory limit scattered without constants.

7. **🟡 MEDIUM: No pytest.ini / pyproject.toml asyncio mode** — `pytest-asyncio>=0.23.0` requires explicit `asyncio_mode` configuration; tests may behave inconsistently.

8. **🟢 LOW: Circular Import Risk** — Logger imports orchestrator components; orchestrator imports logger. Currently works but fragile to refactoring.

9. **🟢 LOW: Scripts Directory Not a Package** — `scripts/` has no `__init__.py` and `conftest.py` tries to import from it via `sys.path` manipulation. This is fragile.

10. **🟢 LOW: Inconsistent Error Handling** — Some functions use `return None`, others raise exceptions, others use `SafetyException`. No unified error handling pattern documented.

11. **🔴 HIGH: Stale Data / Zombie Session Risk** — System can hang if WebSocket stops sending data without disconnecting. Requires active "heartbeat" monitoring.

12. **🟡 MEDIUM: Inconsistent Trading Symbols** — Mix of `BTCUSD` and `BTCUSDT` usage creates confusion and potential API errors.

---

## 2. System Map

### 2.1 Repo Structure

```
btc-laptop-agents/
├── src/laptop_agents/          # Main package (entrypoint: la CLI)
│   ├── agents/                 # Trading agents (Supervisor, MarketIntake, etc.)
│   ├── alerts/                 # Telegram notifications
│   ├── backtest/               # Backtesting engine
│   ├── commands/               # CLI commands (lifecycle, session, system)
│   ├── core/                   # Core infrastructure (config, logger, orchestrator)
│   │   └── diagnostics/        # Error fingerprinting system
│   ├── dashboard/              # Real-time web dashboard
│   ├── data/providers/         # Market data providers (Bitunix, Mock, etc.)
│   ├── execution/              # Order execution (BitunixBroker)
│   ├── memory/                 # Local state persistence
│   ├── paper/                  # Paper trading broker
│   ├── resilience/             # Circuit breakers, retry logic
│   ├── reporting/              # HTML report generation
│   ├── session/                # Async/timed trading sessions
│   └── trading/                # Trading helpers, signals
├── config/strategies/          # Strategy JSON configs
├── tests/                      # pytest test suite
├── scripts/                    # Utility scripts (not a package)
├── docs/                       # Documentation
├── .workspace/                 # Runtime artifacts (gitignored)
└── .github/workflows/ci.yml    # GitHub Actions CI
```

### 2.2 Runtime Map

| Component | Entrypoint | Description |
|-----------|------------|-------------|
| **CLI** | `la` (pyproject.toml → `laptop_agents.main:app`) | Typer-based CLI |
| **Async Session** | `session/async_session.py:run_async_session()` | Main trading loop (WebSocket) |
| **Timed Session** | `session/timed_session.py:run_timed_session()` | Polling-based trading loop |
| **Paper Broker** | `paper/broker.py:PaperBroker` | Simulated trading |
| **Live Broker** | `execution/bitunix_broker.py:BitunixBroker` | Real Bitunix API |
| **Supervisor** | `agents/supervisor.py:Supervisor` | Agent orchestration |
| **WebSocket** | `data/providers/bitunix_ws.py:BitunixWSProvider` | Real-time market data |

### 2.3 Data Flow

```
[Bitunix/Mock Provider]
         ↓ (candles/ticks)
[MarketIntakeAgent] → normalize
         ↓
[SetupSignalAgent] → detect trade signals
         ↓
[ExecutionRiskSentinelAgent] → risk sizing + gates
         ↓
[PaperBroker / BitunixBroker] → execute orders
         ↓
[JournalCoachAgent] → log to .workspace/
```

### 2.4 How to Run Locally

```powershell
# 1. Install (editable mode with test deps)
pip install -e .[test]

# 2. Create .env from example
copy .env.example .env
# Edit .env with BITUNIX_API_KEY and BITUNIX_API_SECRET

# 3. Verify environment
la doctor --fix

# 4. Run 10-minute paper session
la run --mode live-session --duration 10 --async

# 5. Run tests (currently broken - see Finding #1)
pytest tests/ -v

# 6. Type check
mypy src/laptop_agents --ignore-missing-imports
```

---

## 3. Findings (Prioritized)

### Finding #1: Test Suite Completely Broken (Unicode Encoding)

| Attribute | Value |
|-----------|-------|
| **Severity** | 🔴 Blocker |
| **Category** | Testing / DX |
| **Evidence** | [tests/conftest.py#L42](file:///c:/Users/lovel/trading/btc-laptop-agents/tests/conftest.py#L42), [src/laptop_agents/core/diagnostics/fingerprinter.py#L105](file:///c:/Users/lovel/trading/btc-laptop-agents/src/laptop_agents/core/diagnostics/fingerprinter.py#L105) |

**Problem**: `conftest.py` hooks into `pytest_exception_interact` and calls `fingerprinter.lookup()`. The fingerprinter uses `print(f"✓ MATCH FOUND...")` with a Unicode checkmark. On Windows with cp1252 encoding, this causes `UnicodeEncodeError` and crashes pytest with `INTERNALERROR`.

**Impact**: Zero tests can run. CI would fail on Windows. No ability to verify changes.

**Proposed Fix**:
```python
# fingerprinter.py - replace Unicode with ASCII
print(f"[OK] MATCH FOUND (fingerprint: {fp})")  # instead of ✓
```
Or use `console.print()` from Rich which handles encoding.

**Effort**: S (15 min)
**Risk**: Low
**Acceptance Criteria**: `pytest tests/ -q` completes without INTERNALERROR

---

### Finding #2: 60+ Mypy Type Errors

| Attribute | Value |
|-----------|-------|
| **Severity** | 🔴 High |
| **Category** | Type Safety / Maintainability |
| **Evidence** | `mypy src/laptop_agents --ignore-missing-imports` output |

**Key Issues Identified**:

| File | Issue | Count |
|------|-------|-------|
| `backtest/engine.py` | `float | None` assigned to `float` | 8 |
| `data/providers/bitunix_ws.py` | `websockets` module attributes undefined | 6 |
| `data/providers/bitunix_futures.py` | Exception type incompatibility | 5 |
| `paper/broker.py`, `execution/bitunix_broker.py` | Missing type annotations | 4 |
| `core/config.py` | Pydantic v2 `__fields__` deprecated | 1 |
| Various | Implicit Optional violations (PEP 484) | 12+ |

**Proposed Fix**: Systematic type annotation pass:
1. Add `from __future__ import annotations` to all files
2. Replace `arg: Type = None` with `arg: Optional[Type] = None`
3. Add explicit type annotations to container variables
4. Fix `websockets` imports to use `websockets.legacy.client` or typed stubs

**Effort**: M (2-3 hours)
**Risk**: Medium (requires careful testing)
**Acceptance Criteria**: `mypy src/laptop_agents --ignore-missing-imports --no-error-summary` returns 0 errors

---

### Finding #3: Missing requirements.txt (Docker Build Broken)

| Attribute | Value |
|-----------|-------|
| **Severity** | 🔴 High |
| **Category** | Build / Deploy |
| **Evidence** | [Dockerfile#L7](file:///c:/Users/lovel/trading/btc-laptop-agents/Dockerfile#L7) references `requirements.txt` |

**Problem**: Dockerfile line `COPY requirements.txt .` and `RUN pip install -r requirements.txt` will fail because the file doesn't exist. Only `requirements-dev.txt` exists.

**Proposed Fix**: Either:
1. Create `requirements.txt` from pyproject.toml dependencies, OR
2. Update Dockerfile to use `pip install -e .` directly

Option 2 is cleaner (single source of truth in pyproject.toml):

```dockerfile
# Dockerfile - updated
COPY pyproject.toml .
RUN pip install --no-cache-dir .
```

**Effort**: S (10 min)
**Risk**: Low
**Acceptance Criteria**: `docker build -t btc-laptop-agents:latest .` succeeds

---

### Finding #4: Duplicate Module Implementations

| Attribute | Value |
|-----------|-------|
| **Severity** | 🟠 High |
| **Category** | Maintainability / Code Organization |
| **Evidence** | `core/rate_limiter.py`, `resilience/rate_limiter.py`; `core/config.py`, `core/config_models.py` |

**Problem**: Two rate limiter implementations exist. Two config modules exist with overlapping `RiskConfig` and `StrategyConfig` classes. This creates confusion about which to use and risks divergence.

**Proposed Fix**:
1. Audit both rate limiters; keep `resilience/rate_limiter.py` (fits domain)
2. Delete `core/rate_limiter.py` or re-export from resilience
3. Merge `config.py` and `config_models.py` into `core/config.py`

**Effort**: M (1-2 hours)
**Risk**: Medium (need to verify all imports)
**Acceptance Criteria**: Single rate_limiter module, single config module

---

### Finding #5: Pydantic v2 Deprecated API Usage

| Attribute | Value |
|-----------|-------|
| **Severity** | 🟡 Medium |
| **Category** | Dependency Hygiene |
| **Evidence** | [core/config.py#L75](file:///c:/Users/lovel/trading/btc-laptop-agents/src/laptop_agents/core/config.py#L75) |

**Problem**: `SessionConfig.__fields__.keys()` uses Pydantic v1 API. Pydantic v2 uses `model_fields`.

**Current Code**:
```python
for key in SessionConfig.__fields__.keys():
```

**Proposed Fix**:
```python
for key in SessionConfig.model_fields.keys():
```

**Effort**: S (5 min)
**Risk**: Low
**Acceptance Criteria**: No Pydantic deprecation warnings

---

### Finding #6: Hardcoded Paths and Magic Numbers

| Attribute | Value |
|-----------|-------|
| **Severity** | 🟡 Medium |
| **Category** | Maintainability |
| **Evidence** | Multiple files |

**Examples**:
- [async_session.py#L82](file:///c:/Users/lovel/trading/btc-laptop-agents/src/laptop_agents/session/async_session.py#L82): `cache_path = Path("paper/last_price_cache.json")` (relative path)
- [async_session.py#L758](file:///c:/Users/lovel/trading/btc-laptop-agents/src/laptop_agents/session/async_session.py#L758): `1500` MB memory limit hardcoded
- [async_session.py#L786](file:///c:/Users/lovel/trading/btc-laptop-agents/src/laptop_agents/session/async_session.py#L786): `Path("paper/async_session.lock")` (relative path)

**Proposed Fix**:
1. Add to `constants.py`:
```python
MEMORY_LIMIT_MB = 1500
PRICE_CACHE_PATH = REPO_ROOT / ".workspace" / "paper" / "last_price_cache.json"
SESSION_LOCK_PATH = REPO_ROOT / ".workspace" / "paper" / "async_session.lock"
```
2. Replace all hardcoded paths with constant references

**Effort**: S (30 min)
**Risk**: Low
**Acceptance Criteria**: No relative paths in session code, magic numbers extracted to constants

---

### Finding #7: Missing pytest-asyncio Configuration

| Attribute | Value |
|-----------|-------|
| **Severity** | 🟡 Medium |
| **Category** | Testing |
| **Evidence** | [pyproject.toml#L36-L38](file:///c:/Users/lovel/trading/btc-laptop-agents/pyproject.toml#L36-L38) |

**Problem**: `pytest-asyncio>=0.23.0` requires explicit `asyncio_mode` setting. Current config is empty.

**Proposed Fix**: Add to `[tool.pytest.ini_options]`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

**Effort**: S (2 min)
**Risk**: Low
**Acceptance Criteria**: Async tests run without warnings about asyncio_mode

---

### Finding #8: Circular Import Risk (Logger ↔ Orchestrator)

| Attribute | Value |
|-----------|-------|
| **Severity** | 🟢 Low |
| **Category** | Code Organization |
| **Evidence** | [core/logger.py](file:///c:/Users/lovel/trading/btc-laptop-agents/src/laptop_agents/core/logger.py) imports orchestrator indirectly via handlers |

**Problem**: `AutonomousMemoryHandler` in logger tries to import from scripts which may import orchestrator which imports logger. Currently works due to lazy import, but fragile.

**Proposed Fix**: Move error fingerprinting capture to a separate module that doesn't depend on orchestrator.

**Effort**: M (1 hour)
**Risk**: Low
**Acceptance Criteria**: No circular import warnings with `python -c "from laptop_agents.core.logger import logger"`

---

### Finding #9: Scripts Directory Not a Package

| Attribute | Value |
|-----------|-------|
| **Severity** | 🟢 Low |
| **Category** | Code Organization |
| **Evidence** | [tests/conftest.py#L6-L7](file:///c:/Users/lovel/trading/btc-laptop-agents/tests/conftest.py#L6-L7), [scripts/](file:///c:/Users/lovel/trading/btc-laptop-agents/scripts/) |

**Problem**: `conftest.py` does `sys.path.append(str(PROJECT_ROOT))` to import from scripts. This is fragile and non-standard.

**Proposed Fix**: Either:
1. Move reusable script utilities to `src/laptop_agents/utils/`, OR
2. Add `scripts/__init__.py` and install as separate package

**Effort**: M (1 hour)
**Risk**: Low
**Acceptance Criteria**: No `sys.path` manipulation in test code

---

### Finding #10: Pre-commit Hooks Missing isort and Type Check

| Attribute | Value |
|-----------|-------|
| **Severity** | 🟢 Low |
| **Category** | DX / Code Style |
| **Evidence** | [.pre-commit-config.yaml](file:///c:/Users/lovel/trading/btc-laptop-agents/.pre-commit-config.yaml) |

**Problem**: Pre-commit only runs black and flake8. Missing isort (import sorting) and mypy (type checking). This allows style inconsistencies to slip through.

**Proposed Fix**: Add to `.pre-commit-config.yaml`:
```yaml
- repo: https://github.com/pycqa/isort
  rev: 5.13.2
  hooks:
    - id: isort
- repo: https://github.com/pre-commit/mirrors-mypy
  rev: v1.8.0
  hooks:
    - id: mypy
      additional_dependencies: [pydantic>=2.0]
      args: [--ignore-missing-imports]
```

**Effort**: S (15 min)
**Risk**: Low
**Acceptance Criteria**: `pre-commit run --all-files` includes isort and mypy

---

### Finding #11: Stale Data / Zombie Session Risk

| Attribute | Value |
|-----------|-------|
| **Severity** | 🔴 High |
| **Category** | Resilience / Availability |
| **Evidence** | Recent production incidents (Conversation `6d7f958d`) |

**Problem**: The `BitunixWSProvider` or `AsyncRunner` can enter a "zombie state" where the WebSocket connection stays open but stops receiving data. The current retry logic only handles *exceptions*, not *silence*. This causes the session to hang indefinitely with stale data.

**Impact**: Bot thinks prices are unchanged, potentially holding losing positions or failing to exit.

**Proposed Fix**:
1. Implement a `check_staleness()` method in `MarketDataStore` or `AsyncRunner`.
2. If `last_tick_time` > 60 seconds ago, force a reconnect or session restart.

**Effort**: M (2 hours)
**Risk**: Medium
**Acceptance Criteria**: System automatically restarts if no ticks received for 60s.

---

### Finding #12: Inconsistent Trading Symbols (BTCUSD vs BTCUSDT)

| Attribute | Value |
|-----------|-------|
| **Severity** | 🟡 Medium |
| **Category** | Configuration |
| **Evidence** | `constants.py`, `scripts/`, `docs/` |

**Problem**: The codebase mixes `BTCUSD` (Coin-M) and `BTCUSDT` (USDT-M) symbols. This causes confusion and potential API errors if the wrong endpoint is queried.

**Proposed Fix**:
1. Standardize on `BTCUSDT` (USDT-M) as the primary default.
2. Update `constants.py` to define `DEFAULT_SYMBOL = "BTCUSDT"`.
3. Update all documentation and examples.

**Effort**: S (1 hour)
**Risk**: Low
**Acceptance Criteria**: Grep for `BTCUSD` returns only legacy/intentional references.

---

## 4. Implementation Plan (AI-Executable)

### Phase 1: Critical Fixes (Blockers) — Day 1

#### Step 1.1: Fix Unicode Encoding in Fingerprinter

**Goal**: Make test suite runnable on Windows

**Files to change**:
- `src/laptop_agents/core/diagnostics/fingerprinter.py`

**Edits**:
```python
# Line ~105: Replace Unicode checkmark with ASCII
# OLD: print(f"✓ MATCH FOUND (fingerprint: {fp})")
# NEW: print(f"[OK] MATCH FOUND (fingerprint: {fp})")

# Also check for other Unicode: ✗, ⚠, etc.
```

**Verification**:
```powershell
python -m pytest tests/test_smoke.py -v
# Expected: Tests run without INTERNALERROR
```

---

#### Step 1.2: Fix Dockerfile (Missing requirements.txt)

**Goal**: Docker builds work

**Files to change**:
- `Dockerfile`

**Edit**:
```dockerfile
# Replace lines 7-8:
# OLD:
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# NEW:
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .
```

**Verification**:
```powershell
docker build -t btc-laptop-agents:latest .
# Expected: Build succeeds
```

---

### ✅ CHECKPOINT 1: Tests runnable, Docker builds

---

### Phase 1.5: Resilience & Standardization — Day 1

#### Step 1.3: Implement Stale Data Heartbeat

**Goal**: Prevent zombie sessions

**Files to change**:
- `src/laptop_agents/session/async_session.py`

**Edit**:
- Add `last_tick_time` tracking to `AsyncRunner`
- Add periodic task (every 10s) to check `time.time() - last_tick_time`
- If > 60s, raise `StaleDataException` to trigger restart

#### Step 1.4: Standardize on BTCUSDT

**Goal**: Consistent symbol usage

**Files to change**:
- `src/laptop_agents/constants.py`
- `src/laptop_agents/main.py` (CLI defaults)

**Verification**:
- `la run --help` shows BTCUSDT as default
- Paper trading uses BTCUSDT prices

---

### Phase 2: Type Safety (High Priority) — Day 1-2

#### Step 2.1: Fix Implicit Optional Types

**Goal**: Eliminate PEP 484 Optional violations

**Files to change** (search for `= None` in function signatures):
- `core/logger.py` (lines 151, 211)
- `reporting/html_renderer.py` (lines 39-40)
- `alerts/telegram.py` (line 18)
- `core/orchestrator.py` (line 195)

**Pattern**:
```python
# OLD:
def func(arg: str = None):

# NEW:
from typing import Optional
def func(arg: Optional[str] = None):
```

**Verification**:
```powershell
python -m mypy src/laptop_agents/core/logger.py --ignore-missing-imports
# Expected: 0 errors for these specific files
```

---

#### Step 2.2: Fix Pydantic v2 API

**Goal**: Use Pydantic v2 `model_fields`

**Files to change**:
- `src/laptop_agents/core/config.py` (line 75)

**Edit**:
```python
# OLD:
for key in SessionConfig.__fields__.keys():

# NEW:
for key in SessionConfig.model_fields.keys():
```

**Verification**:
```powershell
python -c "from laptop_agents.core.config import load_session_config; print('OK')"
```

---

#### Step 2.3: Add Missing Type Annotations

**Goal**: Fix container type annotations

**Files to change**:
- `paper/broker.py` (lines 57-59)
- `execution/bitunix_broker.py` (line 36)

**Edits**:
```python
# paper/broker.py
from typing import Set, List, Dict, Any

self.processed_order_ids: Set[str] = set()
self.order_timestamps: List[float] = []
self.order_history: List[Dict[str, Any]] = []
```

---

### ✅ CHECKPOINT 2: mypy errors reduced by 50%+

---

### Phase 3: Code Organization (Medium Priority) — Day 2

#### Step 3.1: Consolidate Rate Limiters

**Goal**: Single rate limiter module

**Actions**:
1. Compare `core/rate_limiter.py` vs `resilience/rate_limiter.py`
2. Keep the more complete one (likely `resilience/`)
3. Update imports across codebase
4. Delete redundant module

**Verification**:
```powershell
python -c "from laptop_agents.resilience.rate_limiter import *; print('OK')"
python -m pytest tests/ -k "rate" -v
```

---

#### Step 3.2: Extract Constants

**Goal**: No hardcoded paths or magic numbers

**Files to change**:
- `src/laptop_agents/constants.py`
- `src/laptop_agents/session/async_session.py`

**Add to constants.py**:
```python
from pathlib import Path

MEMORY_LIMIT_MB = 1500
MAX_WS_ERRORS = 10
WS_ERROR_BACKOFF_SEC = 5.0
PRICE_CACHE_PATH = REPO_ROOT / ".workspace" / "paper" / "last_price_cache.json"
SESSION_LOCK_PATH = REPO_ROOT / ".workspace" / "paper" / "async_session.lock"
```

---

#### Step 3.3: Add pytest-asyncio Configuration

**Goal**: Async tests work reliably

**Files to change**:
- `pyproject.toml`

**Edit**:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

---

### ✅ CHECKPOINT 3: Code organization clean, tests stable

---

### Phase 4: DX Polish (Low Priority) — Day 3

#### Step 4.1: Enhance Pre-commit Hooks

**Files to change**:
- `.pre-commit-config.yaml`

**Edits**: Add isort hook

---

#### Step 4.2: Create AGENTS.md for AI Developers

**Goal**: Provide context for AI coding assistants

**Create**: `AGENTS.md` at repo root

**Content**:
```markdown
# AGENTS.md - AI Developer Guide

## Quick Commands
- **Install**: `pip install -e .[test]`
- **Test**: `pytest tests/ -v --tb=short`
- **Type Check**: `mypy src/laptop_agents --ignore-missing-imports`
- **Lint**: `flake8 src/laptop_agents --max-line-length=120`
- **Format**: `black src/laptop_agents`

## Key Files
- Entrypoint: `src/laptop_agents/main.py`
- Config: `src/laptop_agents/core/config.py`
- Trading Loop: `src/laptop_agents/session/async_session.py`
- Constants: `src/laptop_agents/constants.py`

## Conventions
- Use `Optional[Type]` not `Type = None`
- Use `REPO_ROOT` from constants for all paths
- Log with `from laptop_agents.core.logger import logger`
```

---

### ✅ CHECKPOINT 4: Full DX audit complete

---

## 5. Quick Wins vs Strategic Refactors

### Quick Wins (< 1 day each)

| Item | Effort | Impact |
|------|--------|--------|
| Fix Unicode in fingerprinter | 15 min | Unblocks all tests |
| Fix Dockerfile | 10 min | Enables Docker CI |
| Add pytest-asyncio config | 2 min | Stabilizes async tests |
| Fix Pydantic v2 API | 5 min | Future-proofs config |
| Add AGENTS.md | 30 min | Improves AI dev context |

### Strategic Refactors (Multi-day)

| Item | Effort | Risk | Phased Rollout |
|------|--------|------|----------------|
| Fix all mypy errors | 2-3 days | Medium | File by file, test after each |
| Consolidate duplicate modules | 1-2 days | Medium | Keep old module as alias initially |
| Refactor error handling | 2 days | High | Define base exceptions first, then migrate |
| Extract scripts to package | 1 day | Low | Add `__init__.py`, then update imports |

---

## 6. Definition of Done

### DX
- [ ] `pip install -e .[test]` works first time
- [ ] `la doctor --fix` creates working environment
- [ ] `pytest tests/` runs without INTERNALERROR
- [ ] `docker build` succeeds
- [ ] AGENTS.md exists with quick-start commands

### Test Coverage & Reliability
- [ ] All 51 collected tests pass
- [ ] No flaky tests (3 consecutive runs all pass)
- [ ] Async tests use explicit `asyncio_mode` config
- [ ] CI passes on both Ubuntu and Windows

### CI/Build Stability
- [ ] GitHub Actions CI passes on push
- [ ] mypy returns 0 errors (with `--ignore-missing-imports`)
- [ ] Docker image builds and runs

### Docs & Onboarding
- [ ] README.md accurately reflects current setup
- [ ] docs/ENGINEER.md is up to date
- [ ] AGENTS.md provides AI developer context

### Operational Safety & Security
- [ ] No secrets in logs (logger.py scrub_secrets works)
- [ ] Kill switch tested and documented
- [ ] Hard limits enforced (see hard_limits.py)
- [ ] .env.example covers all required vars

---

## Appendix: Evidence Files

| File | Path | Purpose |
|------|------|---------|
| Entrypoint | [main.py](file:///c:/Users/lovel/trading/btc-laptop-agents/src/laptop_agents/main.py) | CLI registration |
| Config | [config.py](file:///c:/Users/lovel/trading/btc-laptop-agents/src/laptop_agents/core/config.py) | Session/strategy config loading |
| Logger | [logger.py](file:///c:/Users/lovel/trading/btc-laptop-agents/src/laptop_agents/core/logger.py) | Logging + secret scrubbing |
| Async Session | [async_session.py](file:///c:/Users/lovel/trading/btc-laptop-agents/src/laptop_agents/session/async_session.py) | Main trading loop |
| Paper Broker | [broker.py](file:///c:/Users/lovel/trading/btc-laptop-agents/src/laptop_agents/paper/broker.py) | Simulated trading |
| Hard Limits | [hard_limits.py](file:///c:/Users/lovel/trading/btc-laptop-agents/src/laptop_agents/core/hard_limits.py) | Safety constraints |
| CI Config | [ci.yml](file:///c:/Users/lovel/trading/btc-laptop-agents/.github/workflows/ci.yml) | GitHub Actions |
| Dockerfile | [Dockerfile](file:///c:/Users/lovel/trading/btc-laptop-agents/Dockerfile) | Container build |
| Test Conftest | [conftest.py](file:///c:/Users/lovel/trading/btc-laptop-agents/tests/conftest.py) | pytest hooks |
| Fingerprinter | [fingerprinter.py](file:///c:/Users/lovel/trading/btc-laptop-agents/src/laptop_agents/core/diagnostics/fingerprinter.py) | Error KB |

---


## Appendix: Glossary (Common Terms)

| Term | Definition |
|------|------------|
| **BitunixWSProvider** | The primary market data feed. Uses WebSocket to fetch `BTCUSDT` ticks. |
| **AsyncRunner** | The main trading engine logic (`async_session.py`). Orchestrates all agents. |
| **Pulse/Heartbeat** | A mechanism to ensure the system is "alive" and receiving data. Vital for detecting zombie states. |
| **Fingerprinter** | Error diagnosis system that hashes error messages to known solutions. |
| **PaperBroker** | Simulated exchange backend. Tracks balances and orders without real money. |
| **Kill Switch** | Global safety overrides (manual or auto) to shut down trading immediately. |

---

*End of Audit*
