# Tier 1 Workflows Implementation Plan
## Autonomous Execution for Gemini 3 Flash

**Created**: 2026-01-15
**Objective**: Implement four high-frequency, high-impact automation workflows.
**Execution Mode**: Fully autonomous. All non-destructive commands use `SafeToAutoRun: true`.

---

## Overview

This plan implements the following workflows in `.agent/workflows/`:

| Workflow | File | Purpose |
| :--- | :--- | :--- |
| `/pre-commit` | `pre-commit.md` | Gate commits with automated verification. |
| `/health` | `health.md` | One-shot system health check. |
| `/rollback` | `rollback.md` | Safe revert with snapshot. |
| `/audit-plan` | `audit-plan.md` | Verify plan completion status. |

---

## Phase 1: Create `/pre-commit` Workflow

### 1.1 Create File
**File**: `.agent/workflows/pre-commit.md`

```markdown
---
description: Run verification checks before committing. Auto-aborts if any check fails.
---
# Pre-Commit Verification Workflow

> **Goal**: Ensure code quality and prevent broken commits.

## 1. Syntax Check
// turbo
```powershell
python -m compileall src scripts -q
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Syntax errors detected." -ForegroundColor Red; exit 1 }
Write-Host "✓ Syntax OK" -ForegroundColor Green
```

## 2. Run Verification Script
// turbo
```powershell
.\scripts\verify.ps1
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Verification failed." -ForegroundColor Red; exit 1 }
```

## 3. Run Unit Tests
// turbo
```powershell
$env:PYTHONPATH='src'; python -m pytest tests/ -q --tb=short
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Tests failed." -ForegroundColor Red; exit 1 }
Write-Host "✓ All tests passed" -ForegroundColor Green
```

## 4. Check Documentation Links
// turbo
```powershell
python scripts/check_docs_links.py
if ($LASTEXITCODE -ne 0) { Write-Host "WARNING: Broken doc links detected." -ForegroundColor Yellow }
```

## 5. Stage & Status
// turbo
```powershell
git status
Write-Host "Pre-commit checks PASSED. Ready to commit." -ForegroundColor Green
```
```

### 1.2 Verification
```powershell
# // turbo
Test-Path .agent/workflows/pre-commit.md
```

---

## Phase 2: Create `/health` Workflow

### 2.1 Create File
**File**: `.agent/workflows/health.md`

```markdown
---
description: One-shot system health check covering processes, API, heartbeat, kill-switch, and errors.
---
# System Health Check Workflow

> **Goal**: Quickly assess the operational state of the entire system.

## 1. Process Check
// turbo
```powershell
$procs = Get-Process python -ErrorAction SilentlyContinue
if ($procs) {
    Write-Host "✓ Python processes running: $($procs.Count)" -ForegroundColor Green
    $procs | Format-Table Id, CPU, WS -AutoSize
} else {
    Write-Host "⚠ No Python processes detected." -ForegroundColor Yellow
}
```

## 2. API Connectivity
// turbo
```powershell
$env:PYTHONPATH='src'; python scripts/check_live_ready.py
```

## 3. Heartbeat Status
// turbo
```powershell
$hb = Get-Content logs/heartbeat.json -ErrorAction SilentlyContinue | ConvertFrom-Json
if ($hb) {
    $age = [math]::Round(((Get-Date) - [datetime]$hb.timestamp).TotalSeconds)
    if ($age -lt 120) {
        Write-Host "✓ Heartbeat: ${age}s ago" -ForegroundColor Green
    } else {
        Write-Host "⚠ Heartbeat STALE: ${age}s ago" -ForegroundColor Yellow
    }
} else {
    Write-Host "✗ Heartbeat file not found." -ForegroundColor Red
}
```

## 4. Kill Switch Status
// turbo
```powershell
$ks = Get-Content config/KILL_SWITCH.txt -ErrorAction SilentlyContinue
if ($ks -and $ks.Trim().ToUpper() -eq 'TRUE') {
    Write-Host "⚠ KILL SWITCH IS ACTIVE" -ForegroundColor Red
} else {
    Write-Host "✓ Kill switch: OFF" -ForegroundColor Green
}
```

## 5. Recent Errors
// turbo
```powershell
$errors = Get-Content logs/system.jsonl -Tail 100 -ErrorAction SilentlyContinue | Where-Object { $_ -match '"level":\s*"ERROR"' }
if ($errors) {
    Write-Host "⚠ Recent errors found: $($errors.Count)" -ForegroundColor Yellow
    $errors | Select-Object -Last 3
} else {
    Write-Host "✓ No recent errors in logs." -ForegroundColor Green
}
```

## 6. Summary
```powershell
Write-Host "`n=== HEALTH CHECK COMPLETE ===" -ForegroundColor Cyan
```
```

### 2.2 Verification
```powershell
# // turbo
Test-Path .agent/workflows/health.md
```

---

## Phase 3: Create `/rollback` Workflow

### 3.1 Create File
**File**: `.agent/workflows/rollback.md`

```markdown
---
description: Safely revert the last N commits on the current branch with a safety snapshot first.
---
# Rollback Workflow

> **Goal**: Undo recent commits safely, with a backup branch for recovery.

## Prerequisites
- User must specify the number of commits to revert (e.g., `/rollback 2`).
- This workflow assumes the agent receives `$N` as a parameter (default: 1).

## 1. Create Safety Snapshot
// turbo
```powershell
$branch = git branch --show-current
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backupBranch = "backup/${branch}-${timestamp}"
git branch $backupBranch
Write-Host "✓ Safety snapshot created: $backupBranch" -ForegroundColor Green
```

## 2. Show Commits to Revert
// turbo
```powershell
# Default N=1 if not specified by agent
$N = 1
Write-Host "Commits to be reverted:" -ForegroundColor Yellow
git log -$N --oneline
```

## 3. Perform Revert (Requires Approval)
**USER ACTION or Agent Decision**:
```powershell
# Soft reset preserves changes in working directory
git reset --soft HEAD~$N
Write-Host "✓ Reverted $N commit(s). Changes are staged." -ForegroundColor Green
git status
```

## 4. Recovery Instructions
If the rollback was a mistake:
```powershell
# Find the backup branch
git branch | Where-Object { $_ -match 'backup/' }

# Restore from backup
git reset --hard <backup-branch-name>
```
```

### 3.2 Verification
```powershell
# // turbo
Test-Path .agent/workflows/rollback.md
```

---

## Phase 4: Create `/audit-plan` Workflow

### 4.1 Create Helper Script
**File**: `scripts/audit_plan.py`

```python
"""
Audit Plan Verification Script.

Usage: python scripts/audit_plan.py <path_to_plan.md>

Scans a plan markdown file for checkboxes and code references,
then verifies their existence/completion in the codebase.
"""
import sys
import re
from pathlib import Path

def audit_plan(plan_path: str) -> int:
    """Audit a plan file and report completion status."""
    plan = Path(plan_path)
    if not plan.exists():
        print(f"ERROR: Plan file not found: {plan_path}")
        return 1
    
    content = plan.read_text(encoding='utf-8')
    
    # Find all checkbox items
    checkboxes = re.findall(r'- \[([ xX])\] (.+)', content)
    
    # Find all file path references
    file_refs = re.findall(r'`(src/[^`]+\.py|scripts/[^`]+\.py|\.agent/[^`]+\.md)`', content)
    
    print(f"=== Auditing: {plan_path} ===\n")
    
    # Report checkbox status
    completed = sum(1 for c in checkboxes if c[0].lower() == 'x')
    total = len(checkboxes)
    print(f"Checkboxes: {completed}/{total} complete")
    for status, item in checkboxes:
        symbol = "✓" if status.lower() == 'x' else "○"
        print(f"  {symbol} {item[:60]}...")
    
    print()
    
    # Verify file references exist
    missing = []
    for ref in set(file_refs):
        if Path(ref).exists():
            print(f"✓ Exists: {ref}")
        else:
            print(f"✗ MISSING: {ref}")
            missing.append(ref)
    
    print()
    
    # Summary
    if missing:
        print(f"FAILED: {len(missing)} referenced file(s) missing.")
        return 1
    elif total > 0 and completed < total:
        print(f"INCOMPLETE: {total - completed} task(s) remaining.")
        return 0  # Not a failure, just incomplete
    else:
        print("PASSED: All items verified.")
        return 0

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/audit_plan.py <plan.md>")
        sys.exit(1)
    sys.exit(audit_plan(sys.argv[1]))
```

### 4.2 Create Workflow File
**File**: `.agent/workflows/audit-plan.md`

```markdown
---
description: Verify that all items in a plan file have been completed in the codebase.
---
# Audit Plan Workflow

> **Goal**: Validate that a plan's tasks and file references are fulfilled.

## Prerequisites
- User or agent specifies the plan file path (e.g., `/audit-plan .agent/plans/EXAMPLE.md`).

## 1. Run Audit Script
// turbo
```powershell
# Replace <plan.md> with the actual plan file path
python scripts/audit_plan.py .agent/plans/<plan.md>
```

## 2. Interpret Results
- **PASSED**: All checkboxes marked `[x]` and all file references exist.
- **INCOMPLETE**: Some checkboxes remain unchecked.
- **FAILED**: Referenced files are missing from the codebase.

## 3. Next Steps
If the audit fails or is incomplete, review the plan file and address outstanding items.
```

### 4.3 Verification
```powershell
# // turbo
Test-Path scripts/audit_plan.py
Test-Path .agent/workflows/audit-plan.md
```

---

## Phase 5: Final Verification & Commit

### 5.1 Verify All Files Exist
```powershell
# // turbo
@(
    '.agent/workflows/pre-commit.md',
    '.agent/workflows/health.md',
    '.agent/workflows/rollback.md',
    '.agent/workflows/audit-plan.md',
    'scripts/audit_plan.py'
) | ForEach-Object {
    if (Test-Path $_) {
        Write-Host "✓ $_" -ForegroundColor Green
    } else {
        Write-Host "✗ MISSING: $_" -ForegroundColor Red
    }
}
```

### 5.2 Run Pre-Commit on New Files
```powershell
# // turbo
python -m compileall scripts/audit_plan.py -q
```

### 5.3 Commit
```powershell
git add .agent/workflows/pre-commit.md .agent/workflows/health.md .agent/workflows/rollback.md .agent/workflows/audit-plan.md scripts/audit_plan.py
git commit -m "feat(workflow): implement Tier 1 high-frequency automation workflows

- Add /pre-commit: verification gate before commits
- Add /health: one-shot system health check
- Add /rollback: safe commit revert with snapshot
- Add /audit-plan: plan completion verification
- Add scripts/audit_plan.py helper for plan auditing"
git push origin main
```

---

## Phase 6: Update Agent Settings

After execution, the following workflows will be available:

```text
- /pre-commit: Run verification checks before committing. Auto-aborts if any check fails.
- /health: One-shot system health check covering processes, API, heartbeat, kill-switch, and errors.
- /rollback: Safely revert the last N commits on the current branch with a safety snapshot first.
- /audit-plan: Verify that all items in a plan file have been completed in the codebase.
```

---

## Self-Correction Protocol

If any verification step fails:
1. Read the error message.
2. Attempt to fix the issue (e.g., missing file, syntax error).
3. Re-run the verification.
4. If the issue persists after 2 attempts, report the blocker and stop.

---

**END OF PLAN**
