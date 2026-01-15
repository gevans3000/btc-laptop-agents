---
description: Run systematic checks to diagnose issues
---
# Learning Debugger Workflow

> **Goal**: Diagnose issues, recall past solutions, and prevent future regressions.
> **AI Agent Responsibility**: When pending errors are found, the AI MUST provide solutions.

## 1. Check Running Processes
// turbo
```powershell
Get-Process python -ErrorAction SilentlyContinue | Format-Table Id, CPU, WS -AutoSize
```

## 2. Check System Readiness
// turbo
```powershell
$env:PYTHONPATH="src"; python scripts/check_live_ready.py
```

## 3. Extract Recent Errors from Logs
// turbo
```powershell
$errors = Get-Content logs/system.jsonl -Tail 200 -ErrorAction SilentlyContinue | Where-Object { $_ -match '"level":\s*"ERROR"' }
if ($errors) {
    Write-Host "⚠ Found $($errors.Count) recent error(s):" -ForegroundColor Yellow
    $errors | Select-Object -Last 3 | ForEach-Object { Write-Host $_ }
} else {
    Write-Host "✓ No recent errors in logs." -ForegroundColor Green
}
```

## 4. Lookup Known Solutions (Memory Recall)
// turbo
```powershell
python scripts/error_fingerprinter.py list
```

## 5. AI AGENT: Diagnose Pending Errors
// turbo
List all errors that need diagnosis:
```powershell
python scripts/diagnose_pending_errors.py list
```

**AGENT INSTRUCTIONS**: If any pending errors are listed above, you MUST:
1. Analyze the error snippet.
2. Determine the likely root cause based on the codebase.
3. Record the solution using:
```powershell
python scripts/diagnose_pending_errors.py solve "<fingerprint>" "<solution_description>" "<root_cause>"
```
Repeat for each pending error until none remain.

## 6. Run Learned Lint Rules
// turbo
```powershell
python scripts/check_lint_rules.py
```

## 7. Analyze Logs for Patterns
// turbo
```powershell
$latestLog = Get-ChildItem logs/*.log -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latestLog) { Get-Content $latestLog.FullName -Tail 30 }
```

## 8. Clear Cache (Optional)
```powershell
Remove-Item -Recurse -Force __pycache__ -ErrorAction SilentlyContinue
```
