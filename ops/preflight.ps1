Write-Host "=== Laptop Agent Workflow Pre-Flight ===" -ForegroundColor Cyan

# 1. Kill Zombie Agents (Optional but recommended)
$procs = Get-Process python -ErrorAction SilentlyContinue
if ($procs) {
    Write-Host "Found $($procs.Count) Python processes running." -ForegroundColor Yellow
    Write-Host "If you have zombie agents, they might lock files."
    $response = Read-Host "Kill all python processes? (y/n)"
    if ($response -eq 'y') {
        Stop-Process -Name python -Force -ErrorAction SilentlyContinue
        Write-Host "Killed python processes." -ForegroundColor Green
    }
}

# 2. Unlock Workspace
$locks = @("paper/async_session.lock", "paper/unified_state.lock", ".workspace/metrics.lock")
foreach ($lock in $locks) {
    if (Test-Path $lock) {
        Remove-Item $lock -Force
        Write-Host "Removed stale lock: $lock" -ForegroundColor Green
    }
}

# 3. Code Polish (Prevent /go formatting failures)
Write-Host "Polishing code..." -ForegroundColor Cyan
try {
    python -m black src tests
    python -m autoflake --in-place --remove-all-unused-imports --recursive src tests
    Write-Host "Code formatting complete." -ForegroundColor Green
} catch {
    Write-Host "Warning: Formatter tools (black/autoflake) might be missing or failed to run." -ForegroundColor DarkGray
}

# 4. Environment Check
if (-not (Test-Path ".env")) {
    Write-Host "CRITICAL: .env file missing!" -ForegroundColor Red
} else {
    $envContent = Get-Content ".env"
    if ($envContent -match "BITUNIX_API_KEY") {
        Write-Host ".env looks good (Keys detected)." -ForegroundColor Green
    } else {
        Write-Host "Warning: BITUNIX_API_KEY not found in .env" -ForegroundColor Yellow
    }
}

# 5. Clean Python Cache (Avoid import errors)
Write-Host "Cleaning pycache..." -ForegroundColor Cyan
Get-ChildItem -Path . -Include __pycache__ -Recurse -Directory -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
Write-Host "Cache cleaned." -ForegroundColor Green

Write-Host "=== Ready for Workflows (/go, /status) ===" -ForegroundColor Cyan
