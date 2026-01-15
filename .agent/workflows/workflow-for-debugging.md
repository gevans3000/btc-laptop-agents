---
description: Workflow for Debugging
---

# Debugging Workflow

This workflow guides you through systematic debugging of the agent or trading system.

## 1. Check System Status
// turbo
Check if python processes are running:
```powershell
Get-Process python -ErrorAction SilentlyContinue
```

## 2. Check Support Scripts
// turbo
Run the live readiness check to see if environment/API is healthy:
```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe scripts/check_live_ready.py
```

## 3. Analyze Logs
// turbo
Check the last 50 lines of the latest log file:
```powershell
$latestLog = Get-ChildItem logs/*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latestLog) {
    Get-Content $latestLog.FullName -Tail 50
} else {
    Write-Host "No log files found."
}
```

## 4. Run Specific Test (Optional)
If you suspected a specific module, run its tests. Example for indicators:
```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe -m pytest tests/test_indicators.py -v
```

## 5. Clean Artifacts (If needed)
If you suspect cache issues:
```powershell
Remove-Item -Recurse -Force __pycache__ -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .pytest_cache -ErrorAction SilentlyContinue
```
