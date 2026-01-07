#!/usr/bin/env pwsh
# MVP Stop Live - Stops the live paper trading process

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Get repository root
$repoRoot = $PSScriptRoot
while (-not (Test-Path -Path (Join-Path $repoRoot "pyproject.toml"))) {
    $repoRoot = Split-Path $repoRoot -Parent
    if ($repoRoot -eq $null) {
        throw "Cannot find repository root (pyproject.toml)"
    }
}

$paperDir = Join-Path -Path $repoRoot -ChildPath "paper"
$pidFile = Join-Path -Path $paperDir -ChildPath "mvp.pid"

# Check if PID file exists
if (-not (Test-Path $pidFile)) {
    Write-Host "No live process running (no PID file found)" -ForegroundColor Yellow
    exit 0
}

# Read PID
$livePid = (Get-Content $pidFile | Out-String).Trim()
if ($livePid -notmatch '^\d+$') {
    Write-Host "Invalid PID in file: $pidFile" -ForegroundColor Red
    Remove-Item $pidFile -Force
    exit 1
}

# Check if process is running
$process = Get-Process -Id $livePid -ErrorAction SilentlyContinue
if ($process -eq $null) {
    Write-Host "Process $livePid is not running (stale PID file)" -ForegroundColor Yellow
    Remove-Item $pidFile -Force
    exit 0
}

# Stop the process
Write-Host "Stopping live process (PID $livePid)..."
try {
    $process | Stop-Process -Force
    Write-Host "Process $livePid stopped successfully" -ForegroundColor Green
} catch {
    Write-Host "Error stopping process: $_" -ForegroundColor Red
    exit 1
}

# Verify it's stopped
Start-Sleep -Seconds 1
$verifyProcess = Get-Process -Id $livePid -ErrorAction SilentlyContinue
if ($verifyProcess -ne $null) {
    Write-Host "Warning: Process $livePid is still running" -ForegroundColor Yellow
    exit 1
}

# Remove PID file
Remove-Item $pidFile -Force
Write-Host "Removed PID file: $pidFile"

exit 0