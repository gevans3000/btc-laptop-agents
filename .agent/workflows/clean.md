---
description: Safely prune artifacts to prevent disk bloat.
---

# Clean Workflow

> **Goal**: Prune __pycache__, logs, and temporary artifacts in a single atomic operation.

// turbo-all

## 1. Atomic Cleanup
```powershell
Write-Host "Starting Atomic Cleanup..." -ForegroundColor Cyan

# 1. Clean Python Cache
Write-Host " - Pruning Python Cache..." -ForegroundColor White
Get-ChildItem -Path . -Include __pycache__,.pytest_cache -Recurse -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force

# 2. Prune Logs
Write-Host " - Checking logs..." -ForegroundColor White
if (Test-Path .workspace/logs/system.jsonl) {
    $size = (Get-Item .workspace/logs/system.jsonl).Length / 1MB
    if ($size -gt 50) {
        Write-Host "   ⚠ .workspace/logs/system.jsonl is large ($([math]::Round($size, 2)) MB)." -ForegroundColor Yellow
    }
    $logFiles = Get-ChildItem .workspace/logs/system.jsonl.* -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
    if ($logFiles.Count -gt 5) {
        $toDelete = $logFiles | Select-Object -Skip 5
        $toDelete | Remove-Item -Force
        Write-Host "   ✓ Pruned $($toDelete.Count) old logs" -ForegroundColor Green
    }
}

# 3. Clean Temp Artifacts
Write-Host " - Clearing temp artifacts..." -ForegroundColor White
if (Test-Path pytest_temp) {
    Remove-Item -Path pytest_temp/* -Recurse -Force -ErrorAction SilentlyContinue
}
if (Test-Path paper) {
    Get-ChildItem -Path paper/*.html -ErrorAction SilentlyContinue | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-7) } | Remove-Item -Force
}

Write-Host "`n=== CLEANUP COMPLETE ===" -ForegroundColor Green
```
