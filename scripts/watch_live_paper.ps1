<#
Auto-restart watchdog for live paper loop

Usage:
  .\scripts\watch_live_paper.ps1 [-WatchMinutes <minutes>] [-CheckInterval <seconds>]
  
  -WatchMinutes: How long to watch (0 = forever, default 0)
  -CheckInterval: How often to check (default 10 seconds)
#>

param(
    [int]$WatchMinutes = 0,
    [int]$CheckInterval = 10
)

$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $repo

# Ensure directories exist
New-Item -ItemType Directory -Force (Join-Path $repo "logs"), (Join-Path $repo "data") | Out-Null

# Set up watchdog logging
$watchdogLog = Join-Path $repo "logs\watchdog.jsonl"
$watchPidFile = Join-Path $repo "data\watch_live_paper.pid"
$livePidFile = Join-Path $repo "data\live_paper.pid"

# Write watchdog PID
$watchPid = $PID
Set-Content -Path $watchPidFile -Value $watchPid.ToString() -Encoding ASCII

function Write-WatchdogLog {
    param([string]$event, [string]$reason, [int]$attempt, [int]$processId, [string]$runId)
    
    $logEntry = @{
        ts = Get-Date -Format "o"
        event = $event
        reason = $reason
        attempt = $attempt
        pid = $processId
        run_id = $runId
    } | ConvertTo-Json -Compress
    
    try {
        Add-Content -Path $watchdogLog -Value $logEntry -Encoding UTF8
    } catch {
        Write-Host "[WATCHDOG] Failed to write log: $_" -ForegroundColor Red
    }
}

function Get-LivePaperProcess {
    # Check pidfile first
    if (Test-Path $livePidFile) {
        try {
            $pidContent = Get-Content $livePidFile -ErrorAction SilentlyContinue
            if ($pidContent -match '\d+') {
                $process = Get-Process -Id $pidContent -ErrorAction SilentlyContinue
                if ($process -ne $null) {
                    return $process
                }
            }
        } catch {}
    }
    
    # Scan for running processes
    $pythonProcesses = Get-Process -Name python,pythonw -ErrorAction SilentlyContinue
    foreach ($proc in $pythonProcesses) {
        try {
            $cmd = ($proc | Get-WmiObject Win32_Process).CommandLine
            if ($cmd -like "*live_paper_loop.py*" -or $cmd -like "*live_paper_loop*") {
                return $proc
            }
        } catch {}
    }
    return $null
}

function Start-LivePaper {
    $startScript = Join-Path $repo "scripts\start_live_paper.ps1"
    
    try {
        $result = & $startScript -Poll 60 -RunMinutes 0 -Limit 90
        return $true
    } catch {
        Write-Host "[WATCHDOG] Failed to start live paper: $_" -ForegroundColor Red
        return $false
    }
}

Write-Host "[WATCHDOG] Starting watchdog (PID $watchPid)"
Write-WatchdogLog -event "watchdog_start" -reason "initial" -attempt 0 -processId $watchPid -runId "N/A"

$restartAttempt = 0
$backoffSeconds = 10
$maxBackoff = 60

$watchStart = Get-Date
$watchDeadline = if ($WatchMinutes -gt 0) { $watchStart.AddMinutes($WatchMinutes) } else { $null }

while ($true) {
    # Check if we should exit
    if ($watchDeadline -ne $null -and (Get-Date) -gt $watchDeadline) {
        Write-Host "[WATCHDOG] Watch period ended"
        Write-WatchdogLog -event "watchdog_end" -reason "timeout" -attempt $restartAttempt -processId $watchPid -runId "N/A"
        break
    }
    
    # Check if live paper is running
    $liveProcess = Get-LivePaperProcess
    
    if ($liveProcess -eq $null) {
        # Live paper is not running - restart it
        $restartAttempt++
        Write-Host "[WATCHDOG] Live paper not running, restarting (attempt $restartAttempt)..."
        Write-WatchdogLog -event "restart_attempt" -reason "process_not_found" -attempt $restartAttempt -processId $watchPid -runId "N/A"
        
        $success = Start-LivePaper
        
        if ($success) {
            Write-Host "[WATCHDOG] Live paper restarted successfully"
            Write-WatchdogLog -event "restart_success" -reason "start_script_ok" -attempt $restartAttempt -processId $watchPid -runId "N/A"
            $backoffSeconds = 10  # Reset backoff on success
        } else {
            Write-Host "[WATCHDOG] Failed to restart live paper"
            Write-WatchdogLog -event "restart_failed" -reason "start_script_failed" -attempt $restartAttempt -processId $watchPid -runId "N/A"
            
            # Apply backoff
            if ($backoffSeconds -lt $maxBackoff) {
                $backoffSeconds = [Math]::Min($backoffSeconds * 2, $maxBackoff)
            }
        }
        
        Start-Sleep -Seconds $backoffSeconds
    } else {
        # Live paper is running - just check periodically
        Start-Sleep -Seconds $CheckInterval
    }
}

# Cleanup
if (Test-Path $watchPidFile) {
    Remove-Item $watchPidFile -Force -ErrorAction SilentlyContinue | Out-Null
}

Write-Host "[WATCHDOG] Watchdog stopped"
