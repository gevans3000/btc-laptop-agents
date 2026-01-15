param (
    [int]$TotalDurationMinutes = 10,
    [string]$Symbol = "BTCUSD",
    [string]$Strategy = "default"
)

$StartTime = Get-Date
$EndTime = $StartTime.AddMinutes($TotalDurationMinutes)
$RemainingMinutes = $TotalDurationMinutes

Write-Host "Starting Autonomous Trading Loop for $TotalDurationMinutes minutes..." -ForegroundColor Cyan

while ((Get-Date) -lt $EndTime) {
    $Now = Get-Date
    $RemainingSeconds = ($EndTime - $Now).TotalSeconds
    $RemainingMinutes = [math]::Ceiling($RemainingSeconds / 60)
    
    if ($RemainingMinutes -le 0) { break }
    
    Write-Host "Launching Session: Symbol=$Symbol, Strategy=$Strategy, Remaining=$RemainingMinutes min" -ForegroundColor Yellow
    
    # Run the trading session
    python src/laptop_agents/run.py --mode live-session --duration $RemainingMinutes --symbol $Symbol --strategy $Strategy
    
    $ExitCode = $LASTEXITCODE
    
    if ($ExitCode -eq 0) {
        Write-Host "Session completed successfully." -ForegroundColor Green
        break
    } else {
        Write-Host "Session crashed or exited with error code $ExitCode. Restarting in 5 seconds..." -ForegroundColor Red
        Start-Sleep -Seconds 5
        
        # Check if we should still continue
        if ((Get-Date) -ge $EndTime) {
            Write-Host "Total duration reached during restart delay." -ForegroundColor Cyan
            break
        }
    }
}

Write-Host "Autonomous Loop Finished." -ForegroundColor Cyan
