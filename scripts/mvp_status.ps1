#!/usr/bin/env pwsh
# MVP Status Script - Shows running processes, PID file status, and recent activity

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

# Check for live process using PID file
$pidFile = Join-Path -Path $repoRoot -ChildPath "paper\mvp.pid"
$liveRunning = $false
$livePid = $null

if (Test-Path $pidFile) {
    try {
        $livePid = (Get-Content $pidFile | Out-String).Trim()
        if ($livePid -match '^\d+$') {
            $process = Get-Process -Id $livePid -ErrorAction SilentlyContinue
            if ($process -ne $null) {
                $liveRunning = $true
            } else {
                # Process not found, clean up stale PID file
                Remove-Item $pidFile -Force
                Write-Host "Removed stale PID file: $pidFile" -ForegroundColor Yellow
            }
        } else {
            Write-Host "Invalid PID in file: $pidFile" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Error reading PID file: $_" -ForegroundColor Yellow
    }
}

# Show status
Write-Host "=== MVP STATUS ==="
Write-Host ""

if ($liveRunning) {
    Write-Host "RUNNING (PID $livePid)" -ForegroundColor Green
    Write-Host "To stop: .\scripts\mvp_stop_live.ps1"
} else {
    # Check if PID file exists but process is not running (STALE)
    if (Test-Path $pidFile) {
        Write-Host "STALE (PID file exists but process not running)" -ForegroundColor Yellow
        Write-Host "To clean up: .\scripts\mvp_stop_live.ps1"
    } else {
        Write-Host "OFF" -ForegroundColor Red
        Write-Host "To start: .\scripts\mvp_start_live.ps1"
    }
}

Write-Host ""

# Show how to confirm in plain PowerShell
Write-Host "=== CONFIRMATION COMMANDS ==="
Write-Host ""
Write-Host "To manually check if live process is running:"
Write-Host '  Get-Process python | Where-Object { $_.MainWindowTitle -like "run.py" }'
Write-Host ""
Write-Host "To check PID file contents:"
Write-Host "  if (Test-Path ""$pidFile"") { Get-Content ""$pidFile"" }"
Write-Host ""

# Show last run timestamps
$runsLatest = Join-Path -Path $repoRoot -ChildPath "runs\latest"
$paperDir = Join-Path -Path $repoRoot -ChildPath "paper"

Write-Host "=== LAST RUN TIMESTAMPS ==="
Write-Host ""

if (Test-Path $runsLatest) {
    $summaryHtml = Join-Path -Path $runsLatest -ChildPath "summary.html"
    if (Test-Path $summaryHtml) {
        $lastWriteTime = (Get-Item $summaryHtml).LastWriteTime
        Write-Host "Last summary.html: $lastWriteTime"
    }
    
    $eventsJsonl = Join-Path -Path $runsLatest -ChildPath "events.jsonl"
    if (Test-Path $eventsJsonl) {
        $lastWriteTime = (Get-Item $eventsJsonl).LastWriteTime
        Write-Host "Last events.jsonl: $lastWriteTime"
    }
}

if (Test-Path $paperDir) {
    $paperEvents = Join-Path -Path $paperDir -ChildPath "events.jsonl"
    if (Test-Path $paperEvents) {
        $lastWriteTime = (Get-Item $paperEvents).LastWriteTime
        Write-Host "Last paper events: $lastWriteTime"
    }
    
    $paperTrades = Join-Path -Path $paperDir -ChildPath "trades.csv"
    if (Test-Path $paperTrades) {
        $lastWriteTime = (Get-Item $paperTrades).LastWriteTime
        Write-Host "Last paper trades: $lastWriteTime"
    }
    
    $paperState = Join-Path -Path $paperDir -ChildPath "state.json"
    if (Test-Path $paperState) {
        $lastWriteTime = (Get-Item $paperState).LastWriteTime
        Write-Host "Last paper state: $lastWriteTime"
    }
}

Write-Host ""

# Show last 20 events from correct location (paper/events.jsonl if present else runs/latest/events.jsonl)
Write-Host "=== LAST 20 EVENTS ==="
Write-Host ""

$eventsFile = $null
$paperEventsFile = Join-Path -Path $paperDir -ChildPath "events.jsonl"
$runEventsFile = Join-Path -Path $runsLatest -ChildPath "events.jsonl"

if (Test-Path $paperEventsFile) {
    $eventsFile = $paperEventsFile
    Write-Host "Showing events from: paper/events.jsonl"
} elseif (Test-Path $runEventsFile) {
    $eventsFile = $runEventsFile
    Write-Host "Showing events from: runs/latest/events.jsonl"
}

if ($eventsFile -ne $null) {
    try {
        $events = Get-Content $eventsFile -Tail 20 -ErrorAction Stop
        foreach ($event in $events) {
            Write-Host $event
        }
    } catch {
        Write-Host "Error reading events: $_" -ForegroundColor Yellow
    }
} else {
    Write-Host "No events found"
}

Write-Host ""
Write-Host "=== COMMANDS ==="
Write-Host ""
Write-Host "Verify:      .\scripts\verify.ps1"
Write-Host "Run once:    .\scripts\mvp_run_once.ps1"
Write-Host "Start live:  .\scripts\mvp_start_live.ps1"
Write-Host "Status:      .\scripts\mvp_status.ps1"
Write-Host "Stop live:   .\scripts\mvp_stop_live.ps1"
Write-Host "Open:        .\scripts\mvp_open.ps1"