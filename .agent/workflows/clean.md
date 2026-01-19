---
description: Safely prune artifacts to prevent disk bloat.
---

# Clean Workflow

> **Goal**: Prune __pycache__, logs, and temporary artifacts.

// turbo-all

## 1. Clean Python Cache
```powershell
Write-Host "Cleaning Python Cache..." -ForegroundColor Cyan
Get-ChildItem -Path . -Include __pycache__,.pytest_cache -Recurse -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Write-Host "✓ Done." -ForegroundColor Green
```

## 2. Prune Logs
```powershell
Write-Host "Checking logs..." -ForegroundColor Cyan
# Inspect .workspace/logs
if (Test-Path .workspace/logs/system.jsonl) {
    $size = (Get-Item .workspace/logs/system.jsonl).Length / 1MB
    if ($size -gt 50) {
        Write-Host "⚠ .workspace/logs/system.jsonl is large ($([math]::Round($size, 2)) MB). Consider archiving." -ForegroundColor Yellow
    } else {
        Write-Host "✓ .workspace/logs/system.jsonl is healthy ($([math]::Round($size, 2)) MB)." -ForegroundColor Green
    }

    # Prune old logs if rotated files exist there
    $logFiles = Get-ChildItem .workspace/logs/system.jsonl.* -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
    if ($logFiles.Count -gt 5) {
        $toDelete = $logFiles | Select-Object -Skip 5
        Write-Host "Pruning $($toDelete.Count) old log files in .workspace/logs..." -ForegroundColor Yellow
        $toDelete | Remove-Item -Force
    }
}

# Inspect legacy logs/ folder just in case
if (Test-Path logs/system.jsonl) {
    Write-Host "Found legacy logs/ folder. Checking..." -ForegroundColor Yellow
    $size = (Get-Item logs/system.jsonl).Length / 1MB
    if ($size -gt 50) {
        Write-Host "⚠ logs/system.jsonl is large ($([math]::Round($size, 2)) MB)." -ForegroundColor Yellow
    }
}
Write-Host "✓ Log pruning complete." -ForegroundColor Green
```

## 3. Clean Temp Artifacts
```powershell
Write-Host "Cleaning temporary artifacts..." -ForegroundColor Cyan
if (Test-Path pytest_temp) {
    Remove-Item -Path pytest_temp/* -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "✓ Cleaned pytest_temp/" -ForegroundColor Green
}

if (Test-Path paper) {
    # Delete HTML reports older than 7 days
    Get-ChildItem -Path paper/*.html -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } | Remove-Item -Force
    Write-Host "✓ Pruned old HTML reports in paper/" -ForegroundColor Green
}
```

## 4. Summary
```powershell
Write-Host "`n=== CLEANUP COMPLETE ===" -ForegroundColor Cyan
```
