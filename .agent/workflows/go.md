---
description: One command to verify, commit, and ship code changes autonomously
---

# Go Workflow

> **Goal**: Fully autonomous code verification, commit, and deployment in a single command.

// turbo-all

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

## 4. Unit Tests
```powershell
$env:PYTHONPATH='src'
python -m pytest tests/ -q --tb=short -p no:cacheprovider
if ($LASTEXITCODE -ne 0) { 
    Write-Host "ABORT: Tests failed." -ForegroundColor Red
    exit 1 
}
Write-Host "✓ All tests passed" -ForegroundColor Green
```

## 5. Documentation Links
```powershell
python scripts/check_docs_links.py
if ($LASTEXITCODE -ne 0) { 
    Write-Host "WARNING: Broken doc links detected." -ForegroundColor Yellow 
}
```

## 6. Generate Commit Message
```powershell
# Get changed files and generate semantic commit message
$changedFiles = git --no-pager diff --name-only --cached
if (-not $changedFiles) {
    $changedFiles = git --no-pager diff --name-only
}

if (-not $changedFiles) {
    Write-Host "No changes to commit." -ForegroundColor Yellow
    exit 0
}

# Auto-detect commit type based on files changed
$commitType = "chore"
$scope = ""

if ($changedFiles -match "src/") { $commitType = "feat" }
if ($changedFiles -match "test") { $commitType = "test" }
if ($changedFiles -match "docs/") { $commitType = "docs" }
if ($changedFiles -match "\.agent/") { $commitType = "chore" }
if ($changedFiles -match "scripts/") { $commitType = "chore" }

# Detect scope
if ($changedFiles -match "broker") { $scope = "broker" }
elseif ($changedFiles -match "session") { $scope = "session" }
elseif ($changedFiles -match "orchestrator") { $scope = "orchestrator" }
elseif ($changedFiles -match "workflow") { $scope = "workflow" }

Write-Host "Detected commit type: $commitType" -ForegroundColor Cyan
if ($scope) { Write-Host "Detected scope: $scope" -ForegroundColor Cyan }
```

## 7. Stage and Commit
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

## 8. Push to Remote
```powershell
git push origin main
if ($LASTEXITCODE -ne 0) { 
    Write-Host "ABORT: Push failed." -ForegroundColor Red
    exit 1 
}
Write-Host "✓ Pushed to origin/main" -ForegroundColor Green
```

## 9. Success Summary
```powershell
Write-Host "`n=== DEPLOYMENT COMPLETE ===" -ForegroundColor Green
git --no-pager log -1 --oneline
```
