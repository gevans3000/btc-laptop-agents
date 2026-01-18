<#
.SYNOPSIS
    Operator Console for BTC Laptop Agents
    Use this script to manage the system without touching the code.
#>

$env:PYTHONPATH = "$PWD/src"

function Show-Header {
    Clear-Host
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "   BTC LAPTOP AGENT: OPERATOR CONSOLE" -ForegroundColor Cyan
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "STATUS: " -NoNewline
    if (Test-Path ".agent/CODE_LOCK.md") {
        Write-Host "[LOCKED] PROTOCOL LOCK ACTIVE" -ForegroundColor Yellow
        Write-Host "Do not modify core Python files." -ForegroundColor DarkGray
    } else {
        Write-Host "[UNLOCKED] DEVELOPER MODE" -ForegroundColor Green
        Write-Host "Core modification allowed." -ForegroundColor DarkGray
    }
    Write-Host "==========================================`n" -ForegroundColor Cyan
}

function Show-Menu {
    Show-Header
    Write-Host "1. [+] Quick Health Check (1 min)" -ForegroundColor Green
    Write-Host "   -> Runs testall.ps1 -Fast"
    Write-Host ""
    Write-Host "2. [!] Deep Stress Test (~30 mins)" -ForegroundColor Red
    Write-Host "   -> Runs full stability suite"
    Write-Host ""
    Write-Host "3. [*] Edit Strategy Config" -ForegroundColor Yellow
    Write-Host "   -> Opens config/strategies/scalp_1m_sweep.json"
    Write-Host ""
    Write-Host "4. [=] View Last Trading Report (Visual)" -ForegroundColor White
    Write-Host "   -> Opens the latest chart in your browser"
    Write-Host ""
    Write-Host "5. [?] Backtest (Mock Data)" -ForegroundColor Cyan
    Write-Host "   -> Simulates 1000 candles (Random Walk)"
    Write-Host ""
    Write-Host "6. [$] Backtest (Real Data)" -ForegroundColor Cyan
    Write-Host "   -> Fetches last 1000 candles from Bitunix"
    Write-Host ""
    Write-Host "Q. [x] Quit"
    Write-Host ""
}

$running = $true
while ($running) {
    Show-Menu
    $input = Read-Host "Select an option"

    switch ($input) {
        "1" {
            Write-Host "`nStarting Quick Health Check..." -ForegroundColor Green
            & .\testall.ps1 -Fast
            Read-Host "Press Enter to return..."
        }
        "2" {
            Write-Host "`nStarting Deep Stress Test..." -ForegroundColor Red
            Write-Host "This will take about 30 minutes. Press Ctrl+C to abort." -ForegroundColor Yellow
            & .\testall.ps1
            Read-Host "Press Enter to return..."
        }
        "3" {
            $configPath = "config/strategies/scalp_1m_sweep.json"
            Write-Host "`nOpening $configPath..." -ForegroundColor Yellow
            if (Get-Command "code" -ErrorAction SilentlyContinue) {
                code $configPath
            } else {
                notepad $configPath
            }
        }
        "4" {
            $tradingReport = ".workspace/runs/latest/summary.html"
            $testReport = "testall-report.txt"

            if (Test-Path $tradingReport) {
                Write-Host "`nOpening visual trading report in browser..." -ForegroundColor Green
                Start-Process $tradingReport
            } elseif (Test-Path $testReport) {
                Write-Host "`nNo visual report found. Opening technical test log..." -ForegroundColor Yellow
                Get-Content $testReport | More
            } else {
                Write-Host "`nNo reports found. Run a backtest (Option 5 or 6) first!" -ForegroundColor Red
            }
            Read-Host "`nPress Enter to return..."
        }
        "5" {
            Write-Host "`nRunning Mock Backtest..." -ForegroundColor Cyan
            python src/laptop_agents/main.py run --mode backtest --strategy scalp_1m_sweep --limit 1000 --show
            Read-Host "Press Enter to return..."
        }
        "6" {
            Write-Host "`nRunning Real Data Backtest..." -ForegroundColor Cyan
            python src/laptop_agents/main.py run --mode backtest --source bitunix --strategy scalp_1m_sweep --limit 1000 --show
            Read-Host "Press Enter to return..."
        }
        "q" { $running = $false }
        "Q" { $running = $false }
        Default { Write-Host "Invalid option." -ForegroundColor Red; Start-Sleep 1 }
    }
}

Clear-Host
Write-Host "Operator Console Closed." -ForegroundColor Gray
