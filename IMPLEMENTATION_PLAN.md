# Audit Remediation: Autonomous Implementation Plan

> **Source**: AUDIT_REPORT_2026.md
> **Status**: Near Complete — 2 phases remaining

---

## Completed Phases (1-11)

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Dead Code Purge (`prompts/`, `alerts/`) | ✅ |
| 2 | Documentation & Gitignore Fixes | ✅ |
| 3 | Dependency Cleanup (`websockets`, lockfile) | ✅ |
| 4 | Tooling Unification (Ruff) | ✅ |
| 5 | Scripts Cleanup (archive, README) | ✅ |
| 6 | Config Mutable Default Fix | ✅ |
| 7 | CLI Argparse Removal | ✅ |
| 8 | Circuit Breaker Consolidation | ✅ |
| 9 | Rate Limiter Consolidation | ✅ |
| 10 | Unified Resilience Module | ✅ |
| 11 | Heartbeat Extraction | ✅ |

---

## Phase 12: God Module Refactor - State [TODO]

**Goal**: Reduce `async_session.py` by 30%+ (currently ~1605 lines → target <1300)

### Remaining Work

1. **Identify extractable logic** in `async_session.py`:
   - Funding rate task
   - Order execution helpers
   - Metrics/telemetry collection

2. **Create new modules** under `session/`:
   ```
   session/funding.py     # funding_task()
   session/execution.py   # order execution helpers
   session/metrics.py     # optional telemetry
   ```

3. **Update imports** in `async_session.py` to delegate to extracted modules

4. **Verify line count**:
   ```powershell
   (Get-Content "src/laptop_agents/session/async_session.py").Count
   # Target: <1300
   ```

5. **Run tests + /go workflow**

**Commit**: `refactor(session): extract additional logic to meet 30% reduction`

---

## Phase 13: HTTP Library Consolidation [SKIPPED]

> Deferred: `bitunix_ws.py` not present. Would require significant architectural changes.

---

## Phase 14: Final Verification & Walkthrough [TODO]

### Verification Commands

```powershell
python -m compileall src scripts -q
ruff check src tests
ruff format --check src tests
mypy src/laptop_agents --ignore-missing-imports
pytest tests/ -v --tb=short
la --help
la doctor --fix
```

### Deliverables

- [x] `walkthrough.md` generated
- [x] PR summary created
- [ ] CI green confirmed
- [ ] Final commit pushed

**Commit**: `docs: finalize audit remediation`

---

## Success Criteria

- [x] Zero dead code modules
- [x] Zero duplicate resilience implementations
- [ ] `async_session.py` reduced 30%+ lines
- [x] README matches CI (Python 3.11)
- [ ] All tests pass (final run pending)
- [x] `la run --help` shows all options
