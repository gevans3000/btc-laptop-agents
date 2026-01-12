---
description: Autonomous documentation cleanup and alignment for btc-laptop-agents
---

# Documentation Cleanup Implementation Plan

> **Executor**: Gemini 3 Flash (Autonomous Mode)
> **Created**: 2026-01-12
> **Estimated Time**: 15-20 minutes

// turbo-all

---

## PRE-FLIGHT CHECKS

### Step 0: Verify Environment
```powershell
cd c:\Users\lovel\trading\btc-laptop-agents
git status --porcelain
```
**Expected**: Clean working directory or only untracked files.
**If dirty**: Commit or stash existing changes first.

---

## PHASE 1: Critical Fixes (Priority 1)

### Step 1.1: Fix MIN_RR_RATIO Documentation Conflict

**File**: `docs/SPEC.md`
**Action**: Update line 78 to clarify the difference between hard limit and config default.

Find this line:
```
    *   Risk/Reward: Minimum 1.5R.
```

Replace with:
```
    *   Risk/Reward: Hard limit 1.0R minimum (code: `hard_limits.MIN_RR_RATIO`); Config default: 1.5R.
```

---

### Step 1.2: Add Python Version to SPEC.md

**File**: `docs/SPEC.md`
**Action**: Add a Requirements section after Section 7 (Live Trading).

Insert after the Live Trading section:
```markdown
## 8. System Requirements

| Requirement | Version | Notes |
| :--- | :--- | :--- |
| **Python** | 3.10+ | Required for match statements and type hints |
| **PowerShell** | 5.0+ | Windows built-in is sufficient |
| **OS** | Windows 10/11 | Primary development target |
| **Dependencies** | See `requirements.txt` | Install via `pip install -r requirements.txt` |
```

---

### Step 1.3: Fix UTF-8 Encoding Issues

**Files to fix** (re-save as UTF-8 without BOM):
- `docs/DEV_AGENTS.md`
- `docs/AI_HANDOFF.md`
- `docs/MAP.md`
- `docs/GATES.md`
- `docs/SPEC.md`
- `docs/ORCHESTRATION.md`
- `docs/VERIFY.md`
- `docs/TESTING.md`
- `docs/RUNBOOK.md`
- `docs/QA_VALIDATION_PLAN.md`

**Action for each file**:
1. Read the file content
2. Replace `â€"` with `—` (em-dash)
3. Replace `â†'` with `→` (arrow)
4. Replace any other garbled characters
5. Write back as UTF-8

**PowerShell command to verify encoding**:
```powershell
Get-Content docs\DEV_AGENTS.md -Raw | Select-String "â€"" 
```

---

### Step 1.4: Delete Redundant ASSISTANT_CONTEXT.md

**Action**:
```powershell
Remove-Item docs\ASSISTANT_CONTEXT.md -Force
git add docs\ASSISTANT_CONTEXT.md
```

---

### Step 1.5: Update START_HERE.md After Deletion

**File**: `docs/START_HERE.md`
**Action**: The file should only reference `AI_HANDOFF.md` (which it already does). Verify no references to `ASSISTANT_CONTEXT.md` exist.

---

## PHASE 2: Medium Priority Fixes (Priority 2)

### Step 2.1: Clean Up AUDIT_REPORT.md

**File**: `docs/AUDIT_REPORT.md`
**Actions**:

1. Remove reference to non-existent `RELEASE_READINESS.md` (line ~176)
   - Find: `| \`docs/RELEASE_READINESS.md\` | Full Phase D audit results | [x] |`
   - Delete this line

2. Remove sync pack references (lines ~66-67, ~128, ~162-163)
   - Remove all lines containing `sync_pack` or `~~`

3. Remove specific line number reference (line ~126)
   - Find: `File ends cleanly after \`run_live_paper_trading\` return (line 481)`
   - Replace with: `File ends cleanly after \`run_live_paper_trading\` function`

4. Consolidate duplicate audit sections (keep only one comprehensive section)

---

### Step 2.2: Fix ORCHESTRATION.md Broken Reference

**File**: `docs/ORCHESTRATION.md`
**Action**: Update line 49.

Find:
```
*   **Replay Rule**: `scripts/replay.ps1 <run_id>` must yield the exact same artifacts given the same `candles.json`.
```

Replace with:
```
*   **Replay Rule**: Replaying a run with the same `candles.json` must yield the exact same artifacts. (Script: Planned for future implementation)
```

---

### Step 2.3: Update PHASE_E_PLAN.md Checkmarks

**File**: `docs/PHASE_E_PLAN.md`
**Actions**:

1. Line ~256: Change `[x]` to `[ ]` for `docs/EVENTS.md` (file doesn't exist)
   - Find: `- [x] Document event schema in \`docs/EVENTS.md\``
   - Replace: `- [ ] Document event schema in \`docs/EVENTS.md\``

2. Lines ~260-262: Verify these are `[ ]` not `[x]`:
   - `docs/CONFIG.md` - should be `[ ]`
   - `docs/STRATEGIES.md` - should be `[ ]`

---

## PHASE 3: Low Priority Quality Improvements (Priority 3)

### Step 3.1: Standardize Status Labels

**Add or update status headers in these files**:

| File | Current | Target |
|------|---------|--------|
| `docs/AGENTS.md` | None | `> **Status**: ACTIVE` |
| `docs/AI_HANDOFF.md` | None | `> **Status**: ACTIVE` |
| `docs/DEV_AGENTS.md` | None | `> **Status**: ACTIVE` |
| `docs/GIT_WORKFLOW.md` | None | `> **Status**: ACTIVE` |
| `docs/KNOWN_ISSUES.md` | None | `> **Status**: ACTIVE` |
| `docs/MAP.md` | None | `> **Status**: ACTIVE` |
| `docs/NEXT.md` | None | `> **Status**: ACTIVE` |
| `docs/API_REFERENCE.md` | None | `> **Status**: ACTIVE` |
| `docs/AUDIT_REPORT.md` | None | `> **Status**: SUPERSEDED` |
| `docs/PHASE_E_PLAN.md` | None | `> **Status**: IN PROGRESS` |
| `docs/QA_VALIDATION_PLAN.md` | Exists | Keep as is |
| `docs/START_HERE.md` | None | `> **Status**: ACTIVE` |
| `docs/TESTING.md` | `DRAFT` | Change to `> **Status**: ACTIVE` |

**Format**: Insert after the title line:
```markdown
# Title

> **Status**: ACTIVE
```

---

### Step 3.2: Consider Renaming AGENTS.md (OPTIONAL - SKIP IF UNCERTAIN)

**Proposed**: Rename `docs/AGENTS.md` to `docs/ARCHITECTURE.md`

**If renaming**:
1. `git mv docs/AGENTS.md docs/ARCHITECTURE.md`
2. Update all references:
   - `docs/START_HERE.md`: Change `AGENTS.md` to `ARCHITECTURE.md`
   - `docs/AI_HANDOFF.md`: Change reference if present
   - `docs/DEV_AGENTS.md`: Change reference if present

**Decision**: SKIP this step for now. It's optional and may cause confusion.

---

## PHASE 4: Verification & Commit

### Step 4.1: Verify No Syntax Errors

```powershell
python -m compileall src -q
```
**Expected**: Exit code 0, no output.

---

### Step 4.2: Run Quick Verification

```powershell
.\scripts\verify.ps1 -Mode quick
```
**Expected**: `VERIFY: PASS`

---

### Step 4.3: Review Changes

```powershell
git status
git diff --stat
```

---

### Step 4.4: Stage and Commit

```powershell
git add -A
git commit -m "docs: comprehensive documentation cleanup and alignment

- Fixed MIN_RR_RATIO documentation conflict in SPEC.md
- Added Python version requirements to SPEC.md
- Fixed UTF-8 encoding issues across all docs
- Deleted redundant ASSISTANT_CONTEXT.md
- Removed references to non-existent files
- Cleaned up sync pack references from AUDIT_REPORT.md
- Updated ORCHESTRATION.md broken replay.ps1 reference
- Corrected PHASE_E_PLAN.md checkmarks
- Standardized Status labels across all docs"
```

---

### Step 4.5: Push Changes

```powershell
git push origin HEAD
```

---

## COMPLETION CHECKLIST

Before marking complete, verify:

- [ ] `python -m compileall src -q` passes
- [ ] `.\scripts\verify.ps1 -Mode quick` passes
- [ ] No files contain `â€"` (garbled em-dash)
- [ ] `docs/ASSISTANT_CONTEXT.md` is deleted
- [ ] `docs/SPEC.md` has 1.0R hard limit clarification
- [ ] All docs have Status headers
- [ ] Git commit successful
- [ ] Git push successful

---

## ROLLBACK PROCEDURE

If anything goes wrong:
```powershell
git checkout -- .
git clean -fd
```

Or to revert a commit:
```powershell
git revert HEAD
git push origin HEAD
```

---

## NOTES FOR EXECUTOR

1. **Do not skip verification steps** - Always run `verify.ps1` before committing
2. **UTF-8 encoding is critical** - Use PowerShell `Set-Content -Encoding UTF8` when writing
3. **Preserve existing content** - Only modify what's specified; don't rewrite entire files
4. **Report any unexpected errors** - Don't proceed if verification fails

---

*End of Implementation Plan*
