---
description: Autonomous error diagnosis, solution application, and verification
---

# Fix Workflow

> **Goal**: Detect, diagnose, and resolve errors in a single automated pass.

// turbo-all

## 1. Atomic Fix Pipeline
```powershell
Write-Host "Starting Autonomous Fix Pipeline..." -ForegroundColor Cyan

# 1. Error Extraction & Fingerprinting
Write-Host "[1/4] Scanning logs for errors..." -ForegroundColor White
python scripts/error_fingerprinter.py list

# 2. Diagnosis
Write-Host "[2/4] Diagnosing pending errors..." -ForegroundColor White
python scripts/diagnose_pending_errors.py list

# 3. Environment Reset (Cache/Smoke)
Write-Host "[3/4] Resetting environment & running smoke tests..." -ForegroundColor White
Get-ChildItem -Path . -Filter "__pycache__" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Get-ChildItem -Path . -Filter ".pytest_cache" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

$env:PYTHONPATH="src"
python -m pytest tests/test_pipeline_smoke.py -q --tb=short -p no:cacheprovider

# 4. Final Readiness
Write-Host "[4/4] Final system check..." -ForegroundColor White
python -m laptop_agents doctor

Write-Host "`n=== FIX WORKFLOW COMPLETE ===" -ForegroundColor Green
```
