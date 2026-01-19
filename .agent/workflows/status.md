---
description: Comprehensive system status check for session start or check-in
---

# Status Workflow

> **Goal**: Complete system overview in one command - processes, API, git state, errors, positions.

// turbo-all

## 1. System Status (Process & Heartbeat)
```powershell
python -m laptop_agents status
```

## 2. API & Environment (Doctor)
```powershell
python -m laptop_agents doctor
```

## 3. Resource Usage
```powershell
Write-Host "`n--- RESOURCE USAGE ---" -ForegroundColor Cyan
# Disk Usage
$workspaceSize = (Get-ChildItem .workspace -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB
$logsSize = (Get-ChildItem logs -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB
$total = $workspaceSize + $logsSize

Write-Host "Disk: .workspace/ ($([math]::Round($workspaceSize, 2)) MB), logs/ ($([math]::Round($logsSize, 2)) MB)" -ForegroundColor White
if ($total -gt 500) {
    Write-Host "⚠ WARNING: Total storage > 500MB ($([math]::Round($total, 2)) MB). Run /clean." -ForegroundColor Yellow
} else {
    Write-Host "✓ Storage OK ($([math]::Round($total, 2)) MB)" -ForegroundColor Green
}

# Memory Usage (Current Python Process)
$mem = Get-Process -Id $PID | Select-Object -ExpandProperty WorkingSet64
Write-Host "Session Memory: $([math]::Round($mem / 1MB, 2)) MB" -ForegroundColor White
```

## 4. Connectivity Check
```powershell
Write-Host "`n--- CONNECTIVITY ---" -ForegroundColor Cyan
try {
    $google = Test-Connection -ComputerName www.google.com -Count 1 -ErrorAction Stop
    Write-Host "Internet: Connected (Latency: $($google.ResponseTime)ms)" -ForegroundColor Green
} catch {
    Write-Host "Internet: DISCONNECTED" -ForegroundColor Red
}

try {
    $bitunix = Test-Connection -ComputerName api.bitunix.com -Count 1 -ErrorAction Stop
    Write-Host "Exchange (Bitunix): Reachable (Latency: $($bitunix.ResponseTime)ms)" -ForegroundColor Green
} catch {
    Write-Host "Exchange (Bitunix): UNREACHABLE" -ForegroundColor Yellow
}
```

## 5. Recent Errors
```powershell
$errors = Get-Content .workspace/logs/system.jsonl -Tail 100 -ErrorAction SilentlyContinue | Where-Object { $_ -match '"level":\s*"ERROR"' }
if ($errors) {
    Write-Host "⚠ Recent errors found: $($errors.Count)" -ForegroundColor Yellow
    $errors | Select-Object -Last 3
} else {
    Write-Host "✓ No recent errors in logs." -ForegroundColor Green
}
```

## 6. Git Status
```powershell
Write-Host "`n--- GIT STATUS ---" -ForegroundColor Cyan
$branch = git --no-pager branch --show-current
Write-Host "Branch: $branch" -ForegroundColor White

$status = git --no-pager status --short
if ($status) {
    Write-Host "Uncommitted changes:" -ForegroundColor Yellow
    git --no-pager status --short
} else {
    Write-Host "✓ Working tree clean" -ForegroundColor Green
}
```

## 7. Recent Commits
```powershell
Write-Host "`n--- RECENT COMMITS ---" -ForegroundColor Cyan
git --no-pager log -5 --oneline --decorate
```

## 8. Active Positions Summary
```powershell
if (Test-Path .workspace/latest/state.json) {
    $state = Get-Content .workspace/latest/state.json -Raw | ConvertFrom-Json
    if ($state.summary) {
        Write-Host "Mode: $($state.summary.mode) Symbol: $($state.summary.symbol)" -ForegroundColor White
        Write-Host "Net PnL: $($state.summary.net_pnl)" -ForegroundColor White
    } else {
        Write-Host "No active session summary" -ForegroundColor Gray
    }
} else {
    Write-Host "No state file found" -ForegroundColor Gray
}
```

## 9. Summary
```powershell
Write-Host "`n=== STATUS CHECK COMPLETE ===" -ForegroundColor Cyan
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "Timestamp: $timestamp" -ForegroundColor Gray
```
