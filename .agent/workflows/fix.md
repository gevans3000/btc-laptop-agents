---
description: Autonomous error diagnosis, solution application, and verification
---

# Fix Workflow

> **Goal**: Detect errors, apply known solutions, or queue for agent diagnosis - fully autonomous.

// turbo-all

## 1. Extract Recent Errors
```powershell
Write-Host "=== EXTRACTING ERRORS ===" -ForegroundColor Cyan
$errors = Get-Content logs/system.jsonl -Tail 200 -ErrorAction SilentlyContinue | Where-Object { $_ -match '"level":\s*"ERROR"' }
if ($errors) {
    Write-Host "⚠ Found $($errors.Count) recent error(s)" -ForegroundColor Yellow
    $errors | Select-Object -Last 5 | ForEach-Object { Write-Host $_ -ForegroundColor Red }
} else {
    Write-Host "✓ No recent errors in logs." -ForegroundColor Green
    exit 0
}
```

## 2. Lookup Known Solutions
```powershell
Write-Host "`n=== CHECKING KNOWN SOLUTIONS ===" -ForegroundColor Cyan
python scripts/error_fingerprinter.py list
```

## 3. List Pending Errors
```powershell
Write-Host "`n=== PENDING ERRORS ===" -ForegroundColor Cyan
python scripts/diagnose_pending_errors.py list
```

## 4. Run Learned Lint Rules
```powershell
Write-Host "`n=== CHECKING LINT RULES ===" -ForegroundColor Cyan
python scripts/check_lint_rules.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠ Lint rule violations detected" -ForegroundColor Yellow
}
```

## 5. Clear Python Cache
```powershell
Write-Host "`n=== CLEARING CACHE ===" -ForegroundColor Cyan
Get-ChildItem -Path . -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Get-ChildItem -Path . -Filter ".pytest_cache" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Write-Host "✓ Cache cleared" -ForegroundColor Green
```

## 6. Run Smoke Tests
```powershell
Write-Host "`n=== RUNNING SMOKE TESTS ===" -ForegroundColor Cyan
$env:PYTHONPATH="src"
python -m pytest tests/test_pipeline_smoke.py -q --tb=short -p no:cacheprovider
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Smoke tests passed" -ForegroundColor Green
} else {
    Write-Host "✗ Smoke tests failed" -ForegroundColor Red
}
```

## 7. Verify System Readiness
```powershell
Write-Host "`n=== VERIFYING SYSTEM ===" -ForegroundColor Cyan
python scripts/check_live_ready.py
```

## 8. Summary
```powershell
Write-Host "`n=== FIX WORKFLOW COMPLETE ===" -ForegroundColor Cyan
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  - Review pending errors above" -ForegroundColor White
Write-Host "  - If errors persist, check logs/system.jsonl" -ForegroundColor White
Write-Host "  - Run /status to verify system health" -ForegroundColor White
```

## Agent Instructions
If pending errors are listed in Step 3, the agent MUST:
1. Analyze each error snippet
2. Determine root cause from codebase
3. Apply solution using:
   ```powershell
   python scripts/diagnose_pending_errors.py solve "<fingerprint>" "<solution>" "<root_cause>"
   ```
4. Re-run this workflow to verify fix
5. If fixed, auto-commit with: `fix: resolve <error-type> via /fix workflow`
