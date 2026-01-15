# watchdog_smart.ps1 - Smart Process Supervisor with Heartbeat Monitoring
# Usage: .\scripts\watchdog_smart.ps1 --duration 10

param(
    [int]$Duration = 10,
    [string]$Source = "bitunix",
    [string]$Symbol = "BTCUSDT",
    [int]$HeartbeatTimeoutSec = 120,
    [int]$MaxRestarts = 3
)

$LogFile = "logs/watchdog_smart.log"
$HeartbeatFile = "logs/heartbeat.json"
$PidFile = "paper/live.pid"
$RestartCount = 0

if (!(Test-Path "logs")) { New-Item -ItemType Directory -Path "logs" }

function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $entry = "$ts $Message"
    Add-Content -Path $LogFile -Value $entry
    Write-Host $entry
}

function Get-HeartbeatAge {
    if (!(Test-Path $HeartbeatFile)) { return 9999 }
    try {
        $hb = Get-Content $HeartbeatFile | ConvertFrom-Json
        $now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        return $now - $hb.unix_ts
    } catch {
        return 9999
    }
}

function Start-TradingSession {
    Write-Log "[INFO] Starting trading session..."
    $proc = Start-Process -FilePath ".venv/Scripts/python.exe" `
        -ArgumentList "-m src.laptop_agents.run --mode live-session --duration $Duration --source $Source --symbol $Symbol --async" `
        -PassThru -NoNewWindow -RedirectStandardOutput "logs/live.out.txt" -RedirectStandardError "logs/live.err.txt"
    
    $proc.Id | Out-File -FilePath $PidFile
    Write-Log "[INFO] Started PID: $($proc.Id)"
    return $proc
}

function Stop-TradingSession {
    if (Test-Path $PidFile) {
        $pid = Get-Content $PidFile
        try {
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Write-Log "[INFO] Stopped PID: $pid"
        } catch {}
        Remove-Item $PidFile -ErrorAction SilentlyContinue
    }
}

Write-Log "[INFO] Smart Watchdog Started. Heartbeat timeout: ${HeartbeatTimeoutSec}s, Max restarts: $MaxRestarts"

while ($RestartCount -lt $MaxRestarts) {
    $proc = Start-TradingSession
    $RestartCount++
    
    # Monitor loop
    while (!$proc.HasExited) {
        Start-Sleep -Seconds 10
        
        $age = Get-HeartbeatAge
        if ($age -gt $HeartbeatTimeoutSec) {
            Write-Log "[ERROR] Heartbeat stale (${age}s). Killing hung process..."
            Stop-TradingSession
            break
        }
        
        Write-Log "[HEARTBEAT] Age: ${age}s - OK"
    }
    
    if ($proc.HasExited -and $proc.ExitCode -eq 0) {
        Write-Log "[INFO] Session completed successfully."
        break
    }
    
    Write-Log "[WARN] Session crashed or was killed. Restart $RestartCount / $MaxRestarts"
    Start-Sleep -Seconds 5
}

if ($RestartCount -ge $MaxRestarts) {
    Write-Log "[FATAL] Max restarts exceeded. Giving up."
    # Create alert file
    "Max restarts exceeded at $(Get-Date)" | Out-File -FilePath "logs/alert.txt"
}

Write-Log "[INFO] Smart Watchdog Exiting."
