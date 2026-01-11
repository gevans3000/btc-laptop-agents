# watchdog.ps1 - Process Supervisor for BTC Laptop Agents
# Usage: .\scripts\watchdog.ps1 --mode orchestrated --source bitunix --limit 200 --execution-mode live

param(
    [string]$Mode = "orchestrated",
    [string]$Source = "bitunix",
    [string]$Symbol = "BTCUSD",
    [string]$Interval = "1m",
    [int]$Limit = 200,
    [string]$ExecutionMode = "paper",
    [float]$RiskPct = 1.0,
    [float]$StopBps = 30.0,
    [float]$TpR = 1.5
)

$LogFile = "logs/watchdog.log"
if (!(Test-Path "logs")) { New-Item -ItemType Directory -Path "logs" }

Write-Host "Starting Watchdog for BTC Laptop Agents..."
Write-Host "Args: --mode $Mode --source $Source --limit $Limit --execution-mode $ExecutionMode"

while ($true) {
    # Construct command
    $cmd = "python -m src.laptop_agents.run --mode $Mode --source $Source --symbol $Symbol --interval $Interval --limit $Limit --execution-mode $ExecutionMode --risk-pct $RiskPct --stop-bps $StopBps --tp-r $TpR"
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "$timestamp [INFO] Launching process: $cmd"
    Write-Host "Launching process at $timestamp"

    # Start the process
    $process = Start-Process python -ArgumentList "-m src.laptop_agents.run --mode $Mode --source $Source --symbol $Symbol --interval $Interval --limit $Limit --execution-mode $ExecutionMode --risk-pct $RiskPct --stop-bps $StopBps --tp-r $TpR" -Wait -PassThru -NoNewWindow
    
    $exitCode = $process.ExitCode
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    
    if ($exitCode -ne 0) {
        Add-Content -Path $LogFile -Value "$timestamp [ERROR] Process crashed with exit code $exitCode. Restarting in 10s..."
        Write-Error "Process crashed ($exitCode). Restarting in 10s..."
    }
    else {
        Add-Content -Path $LogFile -Value "$timestamp [INFO] Process exited normally. Restarting in 10s..."
        Write-Host "Process exited normally. Restarting in 10s..."
    }
    
    Start-Sleep -Seconds 10
}
