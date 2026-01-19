---
description: One command to verify, commit, and ship code changes autonomously
---

# Go Workflow

> **Goal**: Fully autonomous code verification, commit, and deployment in a single command.

// turbo-all

## 0. Code Formatting
```powershell
Write-Host "Formatting code..." -ForegroundColor Cyan
python -m autoflake --in-place --remove-all-unused-imports --recursive src tests
python -m black src tests
Write-Host "✓ Formatting complete" -ForegroundColor Green
```

## 1. Syntax Check
```powershell
python -m compileall src scripts -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "ABORT: Syntax errors detected." -ForegroundColor Red
    exit 1
}
Write-Host "✓ Syntax OK" -ForegroundColor Green
```

## 2. Learned Lint Rules
```powershell
python scripts/check_lint_rules.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "ABORT: Learned lint rules violated." -ForegroundColor Red
    exit 1
}
Write-Host "✓ Lint rules OK" -ForegroundColor Green
```

## 3. Verification & Doctor
```powershell
python -m laptop_agents doctor --fix
if ($LASTEXITCODE -ne 0) {
    Write-Host "ABORT: Verification failed." -ForegroundColor Red
    exit 1
}
Write-Host "✓ Verification OK" -ForegroundColor Green
```

## 4. Type Safety (mypy)
```powershell
$env:PYTHONPATH='src'
python -m mypy src/laptop_agents --ignore-missing-imports
if ($LASTEXITCODE -ne 0) {
    Write-Host "ABORT: Type checks failed." -ForegroundColor Red
    exit 1
}
Write-Host "✓ Type safety OK" -ForegroundColor Green
```

## 5. Unit Tests
```powershell
$env:PYTHONPATH='src'
python -m pytest tests/ -n auto -q --tb=short -p no:cacheprovider --basetemp=./pytest_temp
if ($LASTEXITCODE -ne 0) {
    Write-Host "ABORT: Tests failed." -ForegroundColor Red
    exit 1
}
Write-Host "✓ All tests passed" -ForegroundColor Green
```

## 6. Documentation Links
```powershell
python scripts/check_docs_links.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: Broken doc links detected." -ForegroundColor Yellow
}
```

## 7. Generate Commit Message
```powershell
# Get changed files and generate semantic commit message
$stagedFiles = git --no-pager diff --name-only --cached
if (-not $stagedFiles) {
    git add .
    $stagedFiles = git --no-pager diff --name-only --cached
}

if (-not $stagedFiles) {
    Write-Host "No changes to commit." -ForegroundColor Yellow
    exit 0
}

# Auto-detect commit type based on files changed
$commitType = "chore"
$scope = ""

if ($stagedFiles -match "src/") { $commitType = "feat" }
if ($stagedFiles -match "test") { $commitType = "test" }
if ($stagedFiles -match "docs/") { $commitType = "docs" }
if ($stagedFiles -match "\.agent/") { $commitType = "chore" }
if ($stagedFiles -match "scripts/") { $commitType = "chore" }

# Detect scope intelligently
if ($stagedFiles -match "src/laptop_agents/paper") { $scope = "paper" }
elseif ($stagedFiles -match "src/laptop_agents/execution") { $scope = "execution" }
elseif ($stagedFiles -match "src/laptop_agents/strategy") { $scope = "strategy" }
elseif ($stagedFiles -match "src/laptop_agents/backtest") { $scope = "backtest" }
elseif ($stagedFiles -match "src/laptop_agents/session") { $scope = "session" }
elseif ($stagedFiles -match "src/laptop_agents/orchestrator") { $scope = "orchestrator" }
elseif ($stagedFiles -match "docs/") { $scope = "docs" }
elseif ($stagedFiles -match "workflow") { $scope = "workflow" }

Write-Host "Detected commit type: $commitType" -ForegroundColor Cyan
if ($scope) { Write-Host "Detected scope: $scope" -ForegroundColor Cyan }
```

## 8. Stage and Commit
```powershell
git add .
git --no-pager status

# Build commit message
$message = if ($scope) { "${commitType}(${scope}): auto-commit via /go workflow" } else { "${commitType}: auto-commit via /go workflow" }

git commit -m $message
if ($LASTEXITCODE -ne 0) {
    Write-Host "ABORT: Commit failed." -ForegroundColor Red
    exit 1
}
Write-Host "✓ Committed: $message" -ForegroundColor Green
```

## 9. Push to Remote
```powershell
git push origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "ABORT: Push failed." -ForegroundColor Red
    exit 1
}
Write-Host "✓ Pushed to origin/main" -ForegroundColor Green
```

## 10. Success Summary
```powershell
Write-Host "`n=== DEPLOYMENT COMPLETE ===" -ForegroundColor Green
git --no-pager log -1 --oneline
```
