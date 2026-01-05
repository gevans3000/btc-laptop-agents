param(
    [switch]$StopWatchdog = $false
)

$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $repo
$pidFile = Join-Path $repo "data\live_paper.pid"
$watchPidFile = Join-Path $repo "data\watch_live_paper.pid"

function GetPid($p) {
    if(!(Test-Path $p)) { return $null }
    $t = Get-Content $p -Raw -ErrorAction SilentlyContinue
    if($null -eq $t) { return $null }
    $m = [regex]::Match($t, "\d+")
    if($m.Success) { return [int]$m.Value }
    return $null
}

$procId = GetPid $pidFile
$success = $false

if ($procId) {
    try {
        # Try graceful stop first
        Stop-Process -Id $procId -ErrorAction SilentlyContinue | Out-Null
        Start-Sleep -Milliseconds 500
        
        # If still running, force kill
        if (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
            & taskkill /PID $procId /T /F | Out-Null
        }
        $success = $true
    } catch {
        $success = $false
    }
}

if (Test-Path $pidFile) {
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue | Out-Null
}

# Optionally stop watchdog
if ($StopWatchdog -and (Test-Path $watchPidFile)) {
    $watchProcId = GetPid $watchPidFile
    if ($watchProcId) {
        try {
            Stop-Process -Id $watchProcId -Force -ErrorAction SilentlyContinue | Out-Null
            Start-Sleep -Milliseconds 500
            if (Get-Process -Id $watchProcId -ErrorAction SilentlyContinue) {
                & taskkill /PID $watchProcId /T /F | Out-Null
            }
        } catch {}
    }
    if (Test-Path $watchPidFile) {
        Remove-Item $watchPidFile -Force -ErrorAction SilentlyContinue | Out-Null
    }
}

if ($success) {
    Write-Host "Live paper stopped successfully."
} else {
    Write-Host "Live paper stop failed or process was not running."
}
