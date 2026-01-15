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
