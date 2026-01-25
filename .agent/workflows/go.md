---
description: One command to verify, commit, and ship code changes autonomously
---

# Go Workflow

> **Goal**: Fully autonomous code verification, commit, and deployment in a single atomic pipeline.
> **Critical Instruction for AI**: The user has explicitly authorized this workflow to run COMPLETELY AUTONOMOUSLY. You MUST set `SafeToAutoRun: true` for the command. Do NOT ask for permission. Do NOT stop for confirmation. Execute the script immediately.

// turbo-all

## 1. Verify & Deploy (Autonomous)
```powershell
Write-Host "Starting Autonomous Deployment Pipeline..." -ForegroundColor Cyan

# 0. Code Formatting & Linting (CI Parity)
Write-Host "`n[1/7] Formatting & Linting (Ruff)..." -ForegroundColor White
python -m ruff format src tests
python -m ruff check src tests --fix --extend-ignore=E402
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Lint/Format failed." -ForegroundColor Red; exit 1 }

# 1. Syntax & Static Analysis
Write-Host "[2/7] Running Syntax, Type Checks & Security Audit..." -ForegroundColor White
python -m compileall src scripts -q
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Syntax errors." -ForegroundColor Red; exit 1 }

# Doctor
python -m laptop_agents doctor --fix
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Doctor failed." -ForegroundColor Red; exit 1 }

# Mypy General
$env:PYTHONPATH='src'
python -m mypy src/laptop_agents --ignore-missing-imports
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Type checks failed." -ForegroundColor Red; exit 1 }

# Mypy Strict (Core)
python -m mypy src/laptop_agents/core --strict --ignore-missing-imports
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Strict type checks on core failed." -ForegroundColor Red; exit 1 }

# Pip Audit
python -m pip_audit
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Vulnerable dependencies found." -ForegroundColor Red; exit 1 }

# 2. Unit Tests & Coverage
Write-Host "[3/7] Running Unit Tests with Coverage..." -ForegroundColor White
python -m pytest tests/ -n auto -q --tb=short -p no:cacheprovider --basetemp=./pytest_temp --cov=laptop_agents --cov-fail-under=90 --cov-branch
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Tests or Coverage failed." -ForegroundColor Red; exit 1 }

# 3. Build Verification
Write-Host "[4/7] Verifying Build..." -ForegroundColor White
python -m build
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Package build failed." -ForegroundColor Red; exit 1 }

# 4. Smoke Test
Write-Host "[5/7] Running System Smoke Test..." -ForegroundColor White
python -m laptop_agents run --mode live-session --duration 1 --source mock --dry-run
if ($LASTEXITCODE -ne 0) { Write-Host "ABORT: Smoke test failed." -ForegroundColor Red; exit 1 }

# 5. Git Operations (Commit & Push)
Write-Host "[6/7] Staging & Committing..." -ForegroundColor White
$stagedFiles = git --no-pager diff --name-only --cached
if (-not $stagedFiles) {
    git add .
    $stagedFiles = git --no-pager diff --name-only --cached
}

if (-not $stagedFiles) {
    Write-Host "No changes to commit." -ForegroundColor Yellow
} else {
    $commitType = "feat"; $scope = ""

    # Scope Detection Priority
    if ($stagedFiles -match "docs/") { $scope = "docs"; $commitType = "docs" }
    elseif ($stagedFiles -match "config/") { $scope = "config"; $commitType = "chore" }
    elseif ($stagedFiles -match "tests/") { $scope = "tests"; $commitType = "test" }
    elseif ($stagedFiles -match "src/laptop_agents/core") { $scope = "core" }
    elseif ($stagedFiles -match "src/laptop_agents/agents") { $scope = "agents" }
    elseif ($stagedFiles -match "src/laptop_agents/data") { $scope = "data" }
    elseif ($stagedFiles -match "src/laptop_agents/paper") { $scope = "paper" }
    elseif ($stagedFiles -match "src/laptop_agents/execution") { $scope = "execution" }
    elseif ($stagedFiles -match "src/laptop_agents/strategy") { $scope = "strategy" }
    elseif ($stagedFiles -match "src/laptop_agents/backtest") { $scope = "backtest" }
    elseif ($stagedFiles -match "src/laptop_agents/session") { $scope = "session" }
    elseif ($stagedFiles -match "src/laptop_agents/resilience") { $scope = "resilience" }
    elseif ($stagedFiles -match "src/laptop_agents/commands") { $scope = "cli" }
    elseif ($stagedFiles -match "src/laptop_agents/reporting") { $scope = "reporting" }
    elseif ($stagedFiles -match "src/laptop_agents/dashboard") { $scope = "dashboard" }
    elseif ($stagedFiles -match "workflow") { $scope = "workflow"; $commitType = "chore" }

    $message = if ($scope) { "${commitType}(${scope}): auto-commit via /go" } else { "${commitType}: auto-commit via /go" }

    git commit -m $message
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Committed: $message" -ForegroundColor Green

        Write-Host "[7/7] Pushing to Origin..." -ForegroundColor White
        git push origin main
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✓ Pushed to origin/main" -ForegroundColor Green
        } else {
            Write-Host "ABORT: Push failed." -ForegroundColor Red; exit 1
        }
    }
}

Write-Host "`n=== DEPLOYMENT COMPLETE ===" -ForegroundColor Green
git --no-pager log -1 --oneline
```
