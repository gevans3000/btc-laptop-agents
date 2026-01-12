# Documentation Cleanup Implementation Plan

> **Status**: READY FOR EXECUTION  
> **Generated**: 2026-01-12  
> **Executor**: AI Agent (Deterministic)  
> **Estimated Effort**: 30-45 minutes

---

## 1. Assumptions

The following baseline truths govern all decisions in this plan:

| # | Assumption | Rationale |
|---|------------|-----------|
| 1 | The repo is moving toward a **modular orchestrated architecture** | Evidence: `docs/ORCHESTRATION.md`, `docs/PHASE_E_PLAN.md`, code in `src/laptop_agents/agents/` |
| 2 | **Python 3.10+** is the minimum supported version | Evidence: `pyproject.toml` line 9: `requires-python = ">=3.10"` |
| 3 | **Stricter safety limits** are preferred when conflicts exist | User heuristic instruction |
| 4 | The **code is the source of truth** for hard limits | `hard_limits.py`: `MIN_RR_RATIO=1.0`, `MAX_LEVERAGE=20.0`, `MAX_POSITION_SIZE_USD=200000` |
| 5 | **`docs/SPEC.md`** is the canonical documentation authority | Declared in SPEC.md line 6: "Single Source of Truth" |
| 6 | **`task.md`** indicates prior cleanup was performed on 2026-01-12 | Some issues may already be resolved |
| 7 | Files marked `SUPERSEDED` should be retained for history but clearly marked | Prevents confusion without losing context |
| 8 | **UTF-8 without BOM** is the encoding standard | Windows-compatible, GitHub-friendly |
| 9 | The `.agent/` directory contains internal tooling, not public docs | Excluded from public-facing cleanup |
| 10 | **No file renames** unless explicitly necessary | Minimizes link breakage and git history complexity |

---

## 2. Repository Discovery Strategy

### Files Analyzed

| Glob Pattern | Count | Location |
|--------------|-------|----------|
| `*.md` (root) | 2 | `README.md`, `task.md` |
| `docs/*.md` | 18 | Primary documentation |
| `.agent/**/*.md` | 6 | Agent-internal workflows and artifacts |

### Full File Inventory (26 Markdown Files)

```
README.md
task.md
docs/AGENTS.md
docs/AI_HANDOFF.md
docs/API_REFERENCE.md
docs/AUDIT_REPORT.md
docs/DEV_AGENTS.md
docs/GATES.md
docs/GIT_WORKFLOW.md
docs/KNOWN_ISSUES.md
docs/MAP.md
docs/NEXT.md
docs/ORCHESTRATION.md
docs/PHASE_E_PLAN.md
docs/QA_VALIDATION_PLAN.md
docs/RUNBOOK.md
docs/SPEC.md
docs/START_HERE.md
docs/TESTING.md
docs/VERIFY.md
.agent/instructions.md
.agent/DIRECTIVES.md
.agent/workflows/turbo_save.md
.agent/workflows/save-progress.md
.agent/workflows/merge-recovery.md
.agent/workflows/docs-cleanup.md
.agent/workflows/docs-cleanup-plan.md
.agent/artifacts/MARKDOWN_AUDIT_REPORT.md
```

---

## 3. Audit Methodology

### Categorization Approach

1. **Semantic Analysis**: Read each file to understand purpose and audience
2. **Cross-Reference Check**: Identify conflicting values across files
3. **Code Verification**: Compare documentation claims against actual source code
4. **Link Validation**: Check for references to non-existent files
5. **Encoding Inspection**: Detect garbled Unicode characters (UTF-8 issues)
6. **Status Header Audit**: Check for consistent status markers

### Conflict Resolution Heuristics

| Conflict Type | Resolution Rule |
|---------------|-----------------|
| Numeric limits | Code (`hard_limits.py`) wins; document as "Hard limit: X, Config default: Y" |
| Python version | `pyproject.toml` wins (3.10+) |
| Mode defaults | Code wins; document both code and script defaults explicitly |
| Missing files | Remove reference OR add "(Planned)" suffix |
| Duplicate content | Keep authoritative source, mark other as SUPERSEDED |

---

## 4. Issue Taxonomy & Severity

| ID | Issue | Severity | Files Affected | Resolution |
|----|-------|----------|----------------|------------|
| **C1** | `MIN_RR_RATIO` conflict: SPEC says 1.5R, code says 1.0R | P0 Critical | `docs/SPEC.md` | Update to clarify hard limit vs config default |
| **C2** | Hard limits section in RUNBOOK says $50 max daily loss but code says $50 too (VERIFIED MATCH) | P2 Cosmetic | `docs/RUNBOOK.md` | No action needed |
| **C3** | Python version inconsistency | P1 Confusing | `docs/SPEC.md`, `README.md`, `docs/RUNBOOK.md` | Already has Requirements section - verify |
| **E1** | Garbled UTF-8 characters (`—` → `â€"`, `→` → garbled) | P0 Critical | Multiple files | Re-encode as UTF-8 |
| **R1** | Reference to `docs/RELEASE_READINESS.md` (doesn't exist) | P1 Confusing | Possibly in older audit | Remove reference |
| **R2** | Reference to `scripts/replay.ps1` (doesn't exist) | P1 Confusing | `docs/ORCHESTRATION.md` | Already fixed per task.md |
| **R3** | Reference to `docs/EVENTS.md` marked complete but doesn't exist | P1 Confusing | `docs/PHASE_E_PLAN.md` | Uncheck the item |
| **R4** | Reference to `docs/CONFIG.md`, `docs/STRATEGIES.md` (don't exist) | P2 Cosmetic | `docs/PHASE_E_PLAN.md` | Already unchecked or add "(Planned)" |
| **D1** | `docs/AUDIT_REPORT.md` marked SUPERSEDED but still has active content | P2 Cosmetic | `docs/AUDIT_REPORT.md` | Add clear deprecation notice |
| **D2** | Potential duplication: `docs/AGENTS.md` vs `docs/DEV_AGENTS.md` naming confusion | P2 Cosmetic | Both files | Document distinction, consider future rename |
| **F1** | Inconsistent Status labels (some `STATUS`, some `Status`, some missing) | P2 Cosmetic | 10+ files | Standardize to `> **Status**: X` |
| **F2** | Inconsistent table alignment (`:---` vs no alignment) | P2 Cosmetic | Multiple | Standardize to left-align `:---` |
| **F3** | Missing language tags on code blocks | P2 Cosmetic | Some files | Add `powershell`, `python`, `json` tags |

---

## 5. Canonical Source & Conflict Resolution Rules

### Source of Truth Hierarchy

```
1. Source Code (hard_limits.py, pyproject.toml) — ABSOLUTE
2. docs/SPEC.md — Authoritative documentation
3. config/default.json — Runtime defaults (can differ from hard limits)
4. docs/RUNBOOK.md — Operational procedures
5. README.md — User-facing quickstart
6. Other docs — Supporting context
```

### Specific Resolution Decisions

| Conflict | Decision | Justification |
|----------|----------|---------------|
| `MIN_RR_RATIO`: SPEC.md says 1.5R, code says 1.0R | SPEC.md updated to: "Hard limit 1.0R (code); Config default 1.5R" | SPEC.md line 78 already correct per task.md |
| Python version: 3.10+ vs 3.11+ | Keep 3.10+ | `pyproject.toml` is authoritative; 3.10 supports match statements |
| Max Leverage: 20x | Verified consistent | `hard_limits.py` and `docs/RUNBOOK.md` both say 20x |
| Max Position Size: $200,000 | Verified consistent | `hard_limits.py` and `docs/RUNBOOK.md` both say $200,000 |
| Max Daily Loss: $50 | Verified consistent | `hard_limits.py` says $50, `docs/RUNBOOK.md` says $50 |

---

## 6. Markdown Style Guide

### Header Rules

| Rule | Example | Applies To |
|------|---------|------------|
| Use Sentence case for headers | `## System Requirements` not `## SYSTEM REQUIREMENTS` | All H2+ headers |
| H1 is file title only | One `#` per file | All files |
| Status block after H1 | `> **Status**: ACTIVE` | All docs/ files |

### Status Values

| Value | Meaning |
|-------|---------|
| `ACTIVE` | Current, maintained, authoritative |
| `IN PROGRESS` | Actively being developed |
| `DRAFT` | Incomplete, subject to change |
| `SUPERSEDED` | Replaced by another document |
| `DEPRECATED` | Scheduled for removal |

### Code Block Rules

| Rule | Correct | Incorrect |
|------|---------|-----------|
| Always specify language | ` ```powershell ` | ` ``` ` |
| Use `powershell` for PS | ` ```powershell ` | ` ```ps1 ` or ` ```shell ` |
| Use `python` for Python | ` ```python ` | ` ```py ` |
| Use `json` for JSON | ` ```json ` | ` ```javascript ` |

### Table Rules

| Rule | Example |
|------|---------|
| Left-align all columns | `| :--- | :--- |` |
| No trailing whitespace | Trim lines |
| Consistent column widths | Visual alignment preferred |

### Link Rules

| Rule | Example |
|------|---------|
| Use relative paths in docs/ | `[SPEC.md](SPEC.md)` |
| Use `../` for parent directory | `[README](../README.md)` |
| Mark planned docs | `[CONFIG.md](CONFIG.md) (Planned)` |

---

## 7. Step-by-Step Execution Plan

### Phase 0: Pre-Flight Verification

**Duration**: 2 minutes

```powershell
# Step 0.1: Verify clean working directory
cd c:\Users\lovel\trading\btc-laptop-agents
git status --porcelain

# Step 0.2: Create safety checkpoint
git stash push -m "pre-docs-cleanup-checkpoint" --include-untracked

# Step 0.3: Verify compilation
python -m compileall src -q

# Step 0.4: Verify quick tests pass
.\scripts\verify.ps1 -Mode quick
```

**Gate**: Proceed only if all commands succeed.

---

### Phase 1: Encoding Standardization

**Duration**: 5 minutes  
**Files**: All `.md` files with encoding issues

#### Step 1.1: Identify Files with Encoding Issues

Files to check and fix:
- `docs/API_REFERENCE.md` (contains `→` characters)
- `docs/AUDIT_REPORT.md` (contains `—` characters)
- `docs/NEXT.md` (contains `✓` characters)
- `docs/KNOWN_ISSUES.md` (no issues detected)
- `docs/QA_VALIDATION_PLAN.md` (contains `☐`, `≤`, `≥` characters)

**Note**: Per `task.md`, UTF-8 encoding issues were already fixed on 2026-01-12. Verify no regressions.

#### Step 1.2: Verification Command

```powershell
# Check for garbled em-dash pattern
Select-String -Path "docs\*.md" -Pattern "â€"" -List
# Expected: No matches (already fixed)

# Check for garbled arrow pattern
Select-String -Path "docs\*.md" -Pattern "â†'" -List
# Expected: No matches (already fixed)
```

**Action**: If matches found, re-save affected files as UTF-8 without BOM.

---

### Phase 2: Conflict Resolution

**Duration**: 10 minutes

#### Step 2.1: Verify SPEC.md Hard Limits Section (Line 78)

**File**: `docs/SPEC.md`

**Expected Current State** (per task.md):
```markdown
*   Risk/Reward: Hard limit 1.0R minimum (code: `hard_limits.MIN_RR_RATIO`); Config default: 1.5R.
```

**Verification**:
```powershell
Select-String -Path "docs\SPEC.md" -Pattern "Hard limit 1.0R"
# Expected: Match found at line 78
```

**Action**: No change needed if already correct.

#### Step 2.2: Verify System Requirements Section Exists

**File**: `docs/SPEC.md`

**Expected**: Section 8 with Python 3.10+ requirement exists.

**Verification**:
```powershell
Select-String -Path "docs\SPEC.md" -Pattern "Python.*3\.10"
# Expected: Match found
```

**Action**: No change needed if already correct.

#### Step 2.3: Verify RUNBOOK Hard Limits Match Code

**File**: `docs/RUNBOOK.md` (Lines 213-217)

**Expected**:
```markdown
- **Max Position Size**: $200,000 USD.
- **Max Daily Loss**: $50 USD.
- **Max Leverage**: 20.0x.
```

**Verification**: Compare against `hard_limits.py`:
- `MAX_POSITION_SIZE_USD = 200000.0` ✓
- `MAX_DAILY_LOSS_USD = 50.0` ✓
- `MAX_LEVERAGE = 20.0` ✓

**Action**: No change needed.

---

### Phase 3: Reference Cleanup

**Duration**: 10 minutes

#### Step 3.1: Fix ORCHESTRATION.md Broken Reference

**File**: `docs/ORCHESTRATION.md` (Line 49)

**Current State** (per task.md, already fixed):
```markdown
*   **Replay Rule**: Replaying a run with the same `candles.json` must yield the exact same artifacts. (Script: Planned for future implementation)
```

**Verification**:
```powershell
Select-String -Path "docs\ORCHESTRATION.md" -Pattern "replay\.ps1"
# Expected: No match (already removed)
```

**Action**: No change needed if already correct.

#### Step 3.2: Audit PHASE_E_PLAN.md Checkmarks

**File**: `docs/PHASE_E_PLAN.md`

**Items to verify**:

| Line | Item | File Exists? | Should Be |
|------|------|--------------|-----------|
| ~254 | `docs/EVENTS.md` | No | `[ ]` |
| ~259 | `docs/README.md` | Yes | `[ ]` (update not complete) |
| ~260 | `docs/CONFIG.md` | No | `[ ]` |
| ~261 | `docs/RUNBOOK.md` | Yes | Already updated |
| ~262 | `docs/STRATEGIES.md` | No | `[ ]` |

**Action**: Update any incorrectly marked `[x]` to `[ ]` for non-existent files.

**Edit Required**:
```markdown
# Line ~254, change:
- [x] Document event schema in `docs/EVENTS.md`
# To:
- [ ] Document event schema in `docs/EVENTS.md`
```

#### Step 3.3: Clean AUDIT_REPORT.md References

**File**: `docs/AUDIT_REPORT.md`

**Status**: Already marked `SUPERSEDED` (line 4). Verify:
1. No active operational guidance
2. Clear deprecation notice exists
3. Points to new authoritative source

**Verification**:
```powershell
Select-String -Path "docs\AUDIT_REPORT.md" -Pattern "SUPERSEDED"
# Expected: Match at line 4
```

**Action**: No change needed if status is clear.

---

### Phase 4: Status Header Standardization

**Duration**: 10 minutes

#### Step 4.1: Audit Current Status Headers

| File | Current Status | Target Status | Action |
|------|----------------|---------------|--------|
| `docs/AGENTS.md` | None visible | `> **Status**: ACTIVE` | Already has it (check) |
| `docs/AI_HANDOFF.md` | `> **Status**: ACTIVE` | Keep | None |
| `docs/API_REFERENCE.md` | `> **Status**: ACTIVE` | Keep | None |
| `docs/AUDIT_REPORT.md` | `> **Status**: SUPERSEDED` | Keep | None |
| `docs/DEV_AGENTS.md` | `> **Status**: ACTIVE` | Keep | None |
| `docs/GATES.md` | `> **STATUS**: ACTIVE` | `> **Status**: ACTIVE` | Normalize case |
| `docs/GIT_WORKFLOW.md` | `> **Status**: ACTIVE` | Keep | None |
| `docs/KNOWN_ISSUES.md` | `> **Status**: ACTIVE` | Keep | None |
| `docs/MAP.md` | `> **Status**: ACTIVE` | Keep | None |
| `docs/NEXT.md` | `> **Status**: ACTIVE` | Keep | None |
| `docs/ORCHESTRATION.md` | `> **STATUS**: ACTIVE` | `> **Status**: ACTIVE` | Normalize case |
| `docs/PHASE_E_PLAN.md` | `> **Status**: IN PROGRESS` | Keep | None |
| `docs/QA_VALIDATION_PLAN.md` | `> **Status**: ACTIVE` | Keep | None |
| `docs/RUNBOOK.md` | None visible in header | Add status | Add `> **Status**: ACTIVE` |
| `docs/SPEC.md` | `> **Status**: ACTIVE & AUTHORITATIVE` | Keep | None |
| `docs/START_HERE.md` | `> **Status**: ACTIVE` | Keep | None |
| `docs/TESTING.md` | `> **Status**: ACTIVE` | Keep | None |
| `docs/VERIFY.md` | `> **STATUS**: ACTIVE` | `> **Status**: ACTIVE` | Normalize case |

#### Step 4.2: Execute Status Header Fixes

**Files requiring case normalization**:
- `docs/GATES.md`: Line 3
- `docs/ORCHESTRATION.md`: Line 3
- `docs/VERIFY.md`: Line 3

**Edit Pattern**:
```markdown
# Change:
> **STATUS**: ACTIVE
# To:
> **Status**: ACTIVE
```

**File requiring status addition**:
- `docs/RUNBOOK.md`: Insert after line 1

**Edit**:
```markdown
# After "# RUNBOOK.md — Operations Manual", add:

> **Status**: ACTIVE
```

---

### Phase 5: Code Block Language Tag Audit

**Duration**: 5 minutes

#### Step 5.1: Find Untagged Code Blocks

```powershell
# Find code blocks without language tags
Select-String -Path "docs\*.md" -Pattern "^```$" -List
```

**Common fixes needed**:
- Add `powershell` to PowerShell commands
- Add `python` to Python code
- Add `json` to JSON examples
- Add `markdown` to documentation examples

**Action**: Spot-check 3-5 files for missing language tags.

---

### Phase 6: Verification & Commit

**Duration**: 5 minutes

#### Step 6.1: Run Full Verification

```powershell
# Compile check
python -m compileall src -q

# Quick verification
.\scripts\verify.ps1 -Mode quick
```

**Gate**: Both must pass.

#### Step 6.2: Review Changes

```powershell
git status
git diff --stat
```

#### Step 6.3: Stage and Commit

```powershell
git add -A
git commit -m "docs: comprehensive documentation audit and cleanup

Phase 1: Encoding verification (UTF-8 compliance)
Phase 2: Conflict resolution (hard limits aligned with code)
Phase 3: Reference cleanup (broken links fixed)
Phase 4: Status header standardization
Phase 5: Code block language tags

Resolves: Hard limit conflicts, stale references, inconsistent formatting
Verified: All changes pass verify.ps1"
```

#### Step 6.4: Push Changes

```powershell
git push origin HEAD
```

---

## 8. Files & Artifacts to Be Created/Modified

### Files to CREATE

| File | Purpose | Priority |
|------|---------|----------|
| None | All necessary files exist | - |

### Files to UPDATE

| File | Changes | Lines Affected |
|------|---------|----------------|
| `docs/GATES.md` | Normalize `STATUS` → `Status` | Line 3 |
| `docs/ORCHESTRATION.md` | Normalize `STATUS` → `Status` | Line 3 |
| `docs/VERIFY.md` | Normalize `STATUS` → `Status` | Line 3 |
| `docs/RUNBOOK.md` | Add Status header | After line 1 |
| `docs/PHASE_E_PLAN.md` | Uncheck non-existent `docs/EVENTS.md` | Line ~254 |

### Files to DELETE

| File | Reason | Priority |
|------|--------|----------|
| `docs/ASSISTANT_CONTEXT.md` | Already deleted per task.md | Verify only |

### Files to VERIFY (No Changes Expected)

| File | Verification |
|------|--------------|
| `docs/SPEC.md` | Hard limits section correct |
| `docs/RUNBOOK.md` | Hard limits match code |
| `docs/ORCHESTRATION.md` | replay.ps1 reference removed |
| `docs/AUDIT_REPORT.md` | SUPERSEDED status marked |

---

## 9. Acceptance Criteria

### Critical (Must Pass)

| # | Criterion | Verification Command | Expected Result |
|---|-----------|---------------------|-----------------|
| 1 | No compilation errors | `python -m compileall src -q` | Exit code 0 |
| 2 | verify.ps1 passes | `.\scripts\verify.ps1 -Mode quick` | `VERIFY: PASS` |
| 3 | No garbled UTF-8 characters | `Select-String -Path "docs\*.md" -Pattern "â€"" -List` | No matches |
| 4 | SPEC.md has correct hard limit | `Select-String -Path "docs\SPEC.md" -Pattern "Hard limit 1.0R"` | Match found |
| 5 | All status headers use `Status` not `STATUS` | `Select-String -Path "docs\*.md" -Pattern "STATUS"` | No matches |

### High Priority (Should Pass)

| # | Criterion | Verification |
|---|-----------|--------------|
| 6 | No references to non-existent `replay.ps1` | Grep returns empty |
| 7 | No references to deleted `ASSISTANT_CONTEXT.md` | Grep returns empty |
| 8 | PHASE_E_PLAN.md has unchecked non-existent files | Manual review |

### Nice to Have

| # | Criterion | Status |
|---|-----------|--------|
| 9 | All code blocks have language tags | Best effort |
| 10 | Consistent table alignment | Best effort |

---

## 10. Rollback & Safety Strategy

### Pre-Execution Checkpoint

```powershell
# Create named stash before starting
git stash push -m "pre-docs-cleanup-$(Get-Date -Format 'yyyyMMdd-HHmmss')" --include-untracked
```

### During Execution

- Commit after each completed phase (not just at the end)
- Use atomic commits with clear messages

### If Something Goes Wrong

#### Option A: Revert Last Commit
```powershell
git revert HEAD --no-edit
git push origin HEAD
```

#### Option B: Reset to Checkpoint
```powershell
git stash list  # Find the checkpoint stash
git reset --hard HEAD~N  # N = number of commits to undo
git stash pop stash@{0}  # Restore stashed changes
```

#### Option C: Full Reset
```powershell
git fetch origin
git reset --hard origin/main
```

### Emergency Contacts

If documentation becomes corrupt and cannot be recovered:
1. Check `docs/AUDIT_REPORT.md` for prior state documentation
2. Check `.agent/artifacts/MARKDOWN_AUDIT_REPORT.md` for audit findings
3. Check git history: `git log --oneline docs/`

---

## 11. Quick Wins Checklist

These items can be executed immediately with minimal risk:

| # | Action | Command | Risk |
|---|--------|---------|------|
| ✓ | Verify ASSISTANT_CONTEXT.md deleted | `Test-Path docs\ASSISTANT_CONTEXT.md` → False | None |
| ✓ | Verify UTF-8 encoding fixed | `Select-String -Path "docs\*.md" -Pattern "â€"" -List` → Empty | None |
| ✓ | Verify SPEC.md hard limits | `Select-String -Path "docs\SPEC.md" -Pattern "Hard limit 1.0R"` → Match | None |
| ○ | Normalize `STATUS` → `Status` in GATES.md | Edit line 3 | Low |
| ○ | Normalize `STATUS` → `Status` in ORCHESTRATION.md | Edit line 3 | Low |
| ○ | Normalize `STATUS` → `Status` in VERIFY.md | Edit line 3 | Low |
| ○ | Add Status header to RUNBOOK.md | Insert after line 1 | Low |
| ○ | Uncheck EVENTS.md in PHASE_E_PLAN.md | Edit line ~254 | Low |

---

## Appendix A: File Status Summary

| File | Status | Issues Found | Resolution |
|------|--------|--------------|------------|
| `README.md` | ✓ Clean | None | No action |
| `task.md` | ✓ Clean | None | No action |
| `docs/AGENTS.md` | ✓ Clean | None | No action |
| `docs/AI_HANDOFF.md` | ✓ Clean | None | No action |
| `docs/API_REFERENCE.md` | ✓ Clean | None | No action |
| `docs/AUDIT_REPORT.md` | ✓ Clean | SUPERSEDED marked | No action |
| `docs/DEV_AGENTS.md` | ✓ Clean | None | No action |
| `docs/GATES.md` | ⚠ Minor | `STATUS` case | Normalize to `Status` |
| `docs/GIT_WORKFLOW.md` | ✓ Clean | None | No action |
| `docs/KNOWN_ISSUES.md` | ✓ Clean | None | No action |
| `docs/MAP.md` | ✓ Clean | None | No action |
| `docs/NEXT.md` | ✓ Clean | None | No action |
| `docs/ORCHESTRATION.md` | ⚠ Minor | `STATUS` case | Normalize to `Status` |
| `docs/PHASE_E_PLAN.md` | ⚠ Minor | Stale checkmark | Uncheck EVENTS.md |
| `docs/QA_VALIDATION_PLAN.md` | ✓ Clean | None | No action |
| `docs/RUNBOOK.md` | ⚠ Minor | Missing Status header | Add header |
| `docs/SPEC.md` | ✓ Clean | Already fixed | No action |
| `docs/START_HERE.md` | ✓ Clean | None | No action |
| `docs/TESTING.md` | ✓ Clean | None | No action |
| `docs/VERIFY.md` | ⚠ Minor | `STATUS` case | Normalize to `Status` |

---

## Appendix B: Hard Limits Reference

**Source**: `src/laptop_agents/core/hard_limits.py`

| Constant | Value | Documentation Status |
|----------|-------|---------------------|
| `MAX_POSITION_SIZE_USD` | $200,000 | ✓ Documented in RUNBOOK |
| `MAX_DAILY_LOSS_USD` | $50 | ✓ Documented in RUNBOOK |
| `MIN_RR_RATIO` | 1.0 | ✓ Documented in SPEC (with config default 1.5) |
| `MAX_LEVERAGE` | 20.0x | ✓ Documented in RUNBOOK |

---

## Appendix C: Python Version Reference

**Source**: `pyproject.toml` line 9

```toml
requires-python = ">=3.10"
```

**Documentation Status**:
- `README.md` line 178: "Python 3.10+" ✓
- `docs/RUNBOOK.md` line 19: "Python: 3.10 or higher" ✓
- `docs/SPEC.md` Section 8: "Python 3.10+" ✓

---

*End of Implementation Plan*
