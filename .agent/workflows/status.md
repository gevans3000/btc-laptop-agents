---
description: Comprehensive system status check for session start or check-in
---

# Status Workflow

> **Goal**: Complete system overview in one command - processes, API, git state, errors, positions.

// turbo-all

## 1. Process Check
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
```powershell
$env:PYTHONPATH='src'
python scripts/check_live_ready.py
```

## 3. Heartbeat Status
```powershell
if (Test-Path logs/heartbeat.json) {
    $hb = Get-Content logs/heartbeat.json -Raw | ConvertFrom-Json
    $hb_ts = if ($hb.ts) { $hb.ts } else { $hb.timestamp }
    $age = [math]::Round(((Get-Date) - [datetime]$hb_ts).TotalSeconds)
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
```powershell
$ks = Get-Content config/KILL_SWITCH.txt -ErrorAction SilentlyContinue
if ($ks -and $ks.Trim().ToUpper() -eq 'TRUE') {
    Write-Host "⚠ KILL SWITCH IS ACTIVE" -ForegroundColor Red
} else {
    Write-Host "✓ Kill switch: OFF" -ForegroundColor Green
}
```

## 5. Recent Errors
```powershell
$errors = Get-Content logs/system.jsonl -Tail 100 -ErrorAction SilentlyContinue | Where-Object { $_ -match '"level":\s*"ERROR"' }
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
Write-Host "`n--- ACTIVE POSITIONS ---" -ForegroundColor Cyan
if (Test-Path state/paper_broker_state.json) {
    $state = Get-Content state/paper_broker_state.json -Raw | ConvertFrom-Json
    if ($state.pos) {
        Write-Host "Position: $($state.pos.side) $($state.pos.qty) @ $($state.pos.entry)" -ForegroundColor White
        Write-Host "Equity: $($state.current_equity)" -ForegroundColor White
    } else {
        Write-Host "No active position" -ForegroundColor Gray
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
