---
description: Run systematic checks to diagnose issues
---
# Learning Debugger Workflow

> **Goal**: Diagnose issues, recall past solutions, and prevent future regressions.

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
If an error was found in Step 3, check if we've seen it before:
```powershell
# Agent should extract error text from Step 3 and run:
# python scripts/error_fingerprinter.py lookup "<error_text>"
python scripts/error_fingerprinter.py list
```

## 5. Run Learned Lint Rules
// turbo
Check if any known bad patterns have re-entered the codebase:
```powershell
python scripts/check_lint_rules.py
```

## 6. Analyze Logs for Patterns
// turbo
```powershell
$latestLog = Get-ChildItem logs/*.log -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latestLog) { Get-Content $latestLog.FullName -Tail 30 }
```

## 7. Post-Fix Protocol (Manual/Guided)
When you fix a bug, run these commands to capture the learning:

### 7a. Capture the Error in Memory
```powershell
python scripts/error_fingerprinter.py capture "<error_message>" "<solution_description>" "<root_cause>"
```

### 7b. Generate a Regression Test
```powershell
python scripts/add_regression_test.py "<test_name>" "<description>" "<assertion_code>"
```

### 7c. Add a Lint Rule (if applicable)
```powershell
python scripts/check_lint_rules.py add "<regex_pattern>" "<warning_message>" "<bug_reference>"
```

## 8. Clear Cache (Optional)
```powershell
Remove-Item -Recurse -Force __pycache__ -ErrorAction SilentlyContinue
```
