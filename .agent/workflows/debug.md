---
description: Run systematic checks to diagnose issues
---
# Debugging Workflow

## 1. Check Processes
// turbo
```powershell
Get-Process python -ErrorAction SilentlyContinue
```

## 2. Check Readiness
// turbo
```powershell
$env:PYTHONPATH="src"; .\.venv\Scripts\python.exe scripts/check_live_ready.py
```

## 3. Analyze Logs
// turbo
```powershell
$latestLog = Get-ChildItem logs/*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latestLog) { Get-Content $latestLog.FullName -Tail 50 }
```

## 4. Clear Cache (Optional)
```powershell
Remove-Item -Recurse -Force __pycache__ -ErrorAction SilentlyContinue
```

