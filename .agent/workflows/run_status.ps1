# Fast Status Check Script
# Optimized for speed with timeouts and error handling

# 1. System Status
python -m laptop_agents status

# 2. Doctor Check
python -m laptop_agents doctor

# 3. Resource Usage
Write-Host "`n--- RESOURCE USAGE ---" -ForegroundColor Cyan
$workspaceSize = 0
if (Test-Path .workspace) {
    try {
        $workspaceSize = (Get-ChildItem .workspace -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB
    } catch {
        $workspaceSize = 0
    }
}
$logsSize = 0
if (Test-Path logs) {
    $logsSize = (Get-ChildItem logs -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB
}
$total = $workspaceSize + $logsSize

Write-Host "Disk: .workspace/ ($([math]::Round($workspaceSize, 2)) MB), logs/ ($([math]::Round($logsSize, 2)) MB)" -ForegroundColor White
if ($total -gt 500) {
    Write-Host "WARNING: Total storage > 500MB ($([math]::Round($total, 2)) MB). Run /clean." -ForegroundColor Yellow
} else {
    Write-Host "Storage OK ($([math]::Round($total, 2)) MB)" -ForegroundColor Green
}

try {
    $mem = Get-Process -Id $PID -ErrorAction SilentlyContinue | Select-Object -ExpandProperty WorkingSet64
    Write-Host "Session Memory: $([math]::Round($mem / 1MB, 2)) MB" -ForegroundColor White
} catch {
    Write-Host "Memory: N/A" -ForegroundColor Gray
}

# 4. Connectivity Check (with 2s timeout)
Write-Host "`n--- CONNECTIVITY ---" -ForegroundColor Cyan
try {
    $google = Test-Connection -ComputerName 8.8.8.8 -Count 1 -TimeoutSeconds 2 -ErrorAction Stop
    Write-Host "Internet: Connected (Latency: $($google.ResponseTime)ms)" -ForegroundColor Green
} catch {
    Write-Host "Internet: DISCONNECTED or Timeout" -ForegroundColor Red
}

try {
    $bitunix = Test-Connection -ComputerName fapi.bitunix.com -Count 1 -TimeoutSeconds 2 -ErrorAction Stop
    Write-Host "Exchange (Bitunix): Reachable (Latency: $($bitunix.ResponseTime)ms)" -ForegroundColor Green
} catch {
    Write-Host "Exchange (Bitunix): UNREACHABLE or Timeout" -ForegroundColor Yellow
}

# 5. Recent Errors
if (Test-Path .workspace/logs/system.jsonl) {
    $errors = Get-Content .workspace/logs/system.jsonl -Tail 100 -ErrorAction SilentlyContinue | Where-Object { $_ -match '"level":\s*"ERROR"' }
    if ($errors) {
        Write-Host "Recent errors found: $($errors.Count)" -ForegroundColor Yellow
        $errors | Select-Object -Last 3
    } else {
        Write-Host "No recent errors in logs." -ForegroundColor Green
    }
}

# 6. Git Status
Write-Host "`n--- GIT STATUS ---" -ForegroundColor Cyan
$branch = git --no-pager branch --show-current
Write-Host "Branch: $branch" -ForegroundColor White

$status = git --no-pager status --short
if ($status) {
    Write-Host "Uncommitted changes:" -ForegroundColor Yellow
    git --no-pager status --short
} else {
    Write-Host "Working tree clean" -ForegroundColor Green
}

# 7. Recent Commits
Write-Host "`n--- RECENT COMMITS ---" -ForegroundColor Cyan
git --no-pager log -3 --oneline --decorate

# 8. Active Positions Summary
if (Test-Path .workspace/latest/state.json) {
    try {
        $state = Get-Content .workspace/latest/state.json -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json
        if ($state.summary) {
            Write-Host "Mode: $($state.summary.mode) Symbol: $($state.summary.symbol)" -ForegroundColor White
            Write-Host "Net PnL: $($state.summary.net_pnl)" -ForegroundColor White
        } else {
            Write-Host "No active session summary" -ForegroundColor Gray
        }
    } catch {
        Write-Host "State file corrupted or unreadable" -ForegroundColor Red
    }
} else {
    Write-Host "No state file found" -ForegroundColor Gray
}

# 9. Summary
Write-Host "`n=== STATUS CHECK COMPLETE ===" -ForegroundColor Cyan
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "Timestamp: $timestamp" -ForegroundColor Gray
