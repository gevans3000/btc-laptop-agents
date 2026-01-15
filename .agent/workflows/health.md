---
description: One-shot system health check covering processes, API, heartbeat, kill-switch, and errors.
---
# System Health Check Workflow

> **Goal**: Quickly assess the operational state of the entire system.

## 1. Process Check
// turbo
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
// turbo
```powershell
$env:PYTHONPATH='src'; python scripts/check_live_ready.py
```

## 3. Heartbeat Status
// turbo
```powershell
$hb = Get-Content logs/heartbeat.json -ErrorAction SilentlyContinue | ConvertFrom-Json
if ($hb) {
    $age = [math]::Round(((Get-Date) - [datetime]$hb.timestamp).TotalSeconds)
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
// turbo
```powershell
$ks = Get-Content config/KILL_SWITCH.txt -ErrorAction SilentlyContinue
if ($ks -and $ks.Trim().ToUpper() -eq 'TRUE') {
    Write-Host "⚠ KILL SWITCH IS ACTIVE" -ForegroundColor Red
} else {
    Write-Host "✓ Kill switch: OFF" -ForegroundColor Green
}
```

## 5. Recent Errors
// turbo
```powershell
$errors = Get-Content logs/system.jsonl -Tail 100 -ErrorAction SilentlyContinue | Where-Object { $_ -match '"level":\s*"ERROR"' }
if ($errors) {
    Write-Host "⚠ Recent errors found: $($errors.Count)" -ForegroundColor Yellow
    $errors | Select-Object -Last 3
} else {
    Write-Host "✓ No recent errors in logs." -ForegroundColor Green
}
```

## 6. Summary
```powershell
Write-Host "`n=== HEALTH CHECK COMPLETE ===" -ForegroundColor Cyan
```
