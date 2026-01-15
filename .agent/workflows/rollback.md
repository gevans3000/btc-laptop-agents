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
