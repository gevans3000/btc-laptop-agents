Write-Host "Starting Autonomous Deployment Pipeline..." -ForegroundColor Cyan

# 0. Code Formatting
Write-Host "`n[1/5] Formatting code..." -ForegroundColor White
python -m autoflake --in-place --remove-all-unused-imports --recursive src tests
python -m black src tests

# 1. Syntax & Lint Check
Write-Host "[2/5] Running Syntax & Lint Checks..." -ForegroundColor White
python -m compileall src scripts -q
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Syntax errors." -ForegroundColor Red; exit 1 }

python scripts/check_lint_rules.py
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Lint violations." -ForegroundColor Red; exit 1 }

# 2. Doctor & Type Safety
Write-Host "[3/5] Verifying System (Doctor & Mypy)..." -ForegroundColor White
python -m laptop_agents doctor --fix
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Doctor failed." -ForegroundColor Red; exit 1 }

$env:PYTHONPATH = 'src'
python -m mypy src/laptop_agents --ignore-missing-imports
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Type checks failed." -ForegroundColor Red; exit 1 }

# 3. Unit Tests
Write-Host "[4/5] Running Unit Tests..." -ForegroundColor White
python -m pytest tests/ -q --tb=short -p no:cacheprovider --basetemp=./pytest_temp
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Tests failed." -ForegroundColor Red; exit 1 }

# 4. Git Operations
Write-Host "[5/5] Shipping Code..." -ForegroundColor White
$stagedFiles = git --no-pager diff --name-only --cached
if (-not $stagedFiles) {
    git add .
    $stagedFiles = git --no-pager diff --name-only --cached
}

if (-not $stagedFiles) {
    Write-Host "No changes to commit." -ForegroundColor Yellow
}
else {
    $commitType = "feat"
    $scope = ""
    if ($stagedFiles -match "src/laptop_agents/paper") { $scope = "paper" }
    elseif ($stagedFiles -match "src/laptop_agents/execution") { $scope = "execution" }
    elseif ($stagedFiles -match "src/laptop_agents/strategy") { $scope = "strategy" }
    elseif ($stagedFiles -match "src/laptop_agents/backtest") { $scope = "backtest" }
    elseif ($stagedFiles -match "src/laptop_agents/session") { $scope = "session" }
    elseif ($stagedFiles -match "workflow") { $scope = "workflow" }

    $msgStart = "${commitType}: auto-commit via /go"
    if ($scope) {
        $msgStart = "${commitType}(${scope}): auto-commit via /go"
    }

    $message = $msgStart

    git commit -m $message
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Committed: $message" -ForegroundColor Green
        git push origin main
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Pushed to origin/main" -ForegroundColor Green
        }
        else {
            Write-Host "ABORT: Push failed." -ForegroundColor Red; exit 1
        }
    }
}

Write-Host "`n=== DEPLOYMENT COMPLETE ===" -ForegroundColor Green
git --no-pager log -1 --oneline
