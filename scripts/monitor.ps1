# scripts/monitor.ps1 - Real-time HUD for BTC Laptop Agents
# Usage: .\scripts\monitor.ps1

$HeartbeatPath = "logs/heartbeat.json"
$KillSwitchPath = "config/KILL_SWITCH.txt"
$WatchdogLogPath = "logs/watchdog.log"

while ($true) {
    Clear-Host
    $Now = Get-Date
    $NowUTC = $Now.ToUniversalTime()

    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "      BTC LAPTOP AGENTS MONITOR         " -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Local Time: $($Now.ToString('yyyy-MM-dd HH:mm:ss'))"
    Write-Host ""

    # 1. Heartbeat Check
    if (Test-Path $HeartbeatPath) {
        try {
            # Use -Raw and ConvertFrom-Json. Handle potential file locks.
            $HB = Get-Content $HeartbeatPath -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json -ErrorAction SilentlyContinue
            
            if ($HB) {
                $HBTime = [DateTime]::Parse($HB.ts).ToUniversalTime()
                $DiffSeconds = ($NowUTC - $HBTime).TotalSeconds

                if ($DiffSeconds -lt 90) {
                    Write-Host "STATUS:      " -NoNewline
                    Write-Host "ONLINE" -ForegroundColor Green
                }
                else {
                    Write-Host "STATUS:      " -NoNewline
                    Write-Host "STALE/FROZEN (Last: $($DiffSeconds.ToString('F0'))s ago)" -ForegroundColor Red
                }

                Write-Host "SYMBOL:      $($HB.symbol)"
                Write-Host "EQUITY:      $($HB.equity.ToString('C'))"
                Write-Host "PROGRESS:    Candle $($HB.candle_idx)"
            }
            else {
                Write-Host "STATUS:      READING HEARTBEAT..." -ForegroundColor Yellow
            }
        }
        catch {
            Write-Host "STATUS:      FILE LOCKED/READ ERROR" -ForegroundColor Yellow
        }
    }
    else {
        Write-Host "STATUS:      WAITING FOR DATA..." -ForegroundColor Gray
    }

    # 2. Kill Switch Check
    if (Test-Path $KillSwitchPath) {
        $KS = Get-Content $KillSwitchPath -ErrorAction SilentlyContinue
        if ($KS -match "TRUE") {
            Write-Host "KILL SWITCH: " -NoNewline
            Write-Host "ACTIVE" -ForegroundColor Red
        }
        else {
            Write-Host "KILL SWITCH: " -NoNewline
            Write-Host "READY" -ForegroundColor Green
        }
    }
    else {
        Write-Host "KILL SWITCH: NOT FOUND" -ForegroundColor Gray
    }

    Write-Host ""
    Write-Host "RECENT ACTIVITY (watchdog.log):" -ForegroundColor White
    if (Test-Path $WatchdogLogPath) {
        Get-Content $WatchdogLogPath -Tail 5 -ErrorAction SilentlyContinue | ForEach-Object {
            Write-Host "  $_" -ForegroundColor DarkGray
        }
    }
    else {
        Write-Host "  No activity logs found." -ForegroundColor DarkGray
    }

    Write-Host ""
    Write-Host "Press Ctrl+C to exit." -ForegroundColor DarkGray
    
    Start-Sleep -Seconds 3
}
