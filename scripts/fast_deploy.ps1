$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'Stop'

# --- 1. Check Verification Report ---
$reportPath = ".workspace\verify_report.json"
if (-not (Test-Path $reportPath)) {
    Write-Host "ERROR: verify_report.json not found." -ForegroundColor Red
    Write-Host "Action: Run '.\verify_local.ps1' first." -ForegroundColor Yellow
    exit 1
}

try {
    $report = Get-Content $reportPath -Raw | ConvertFrom-Json
} catch {
    Write-Host "ERROR: Corrupt verify_report.json" -ForegroundColor Red
    exit 1
}

# Time Check (15m warning)
$reportTime = [DateTime]::Parse($report.timestamp)
$age = (Get-Date) - $reportTime
if ($age.TotalMinutes -gt 15) {
    Write-Host "WARNING: Report is $($age.TotalMinutes.ToString('F0')) mins old." -ForegroundColor Yellow
}

# Failure Check
$failed = $report.steps.PSObject.Properties | Where-Object { $_.Value.status -ne "pass" }
if ($failed) {
    Write-Host "`nFAILED STEPS DETECTED:" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host "  - $($_.Name): $($_.Value.status)" -ForegroundColor Red }
    exit 1
}
Write-Host "✓ Verification Passed" -ForegroundColor Green

# --- 2. Git Operations ---
$staged = git diff --name-only --cached
if (-not $staged) {
    git add .
    $staged = git diff --name-only --cached
}

if (-not $staged) {
    Write-Host "No changes to commit." -ForegroundColor Yellow
    exit 0
}

# Scope Detection
$scope = ""
$type = "feat"
if ($staged -match "docs/") { $scope = "docs"; $type = "docs" }
elseif ($staged -match "config/") { $scope = "config"; $type = "chore" }
elseif ($staged -match "tests/") { $scope = "tests"; $type = "test" }
elseif ($staged -match "src/laptop_agents/core") { $scope = "core" }
elseif ($staged -match "src/laptop_agents/agents") { $scope = "agents" }
elseif ($staged -match "src/laptop_agents/strategy") { $scope = "strategy" }
elseif ($staged -match "workflow") { $scope = "workflow"; $type = "chore" }
elseif ($staged -match "src/") { $scope = "app" }

$msg = if ($scope) { "${type}(${scope}): auto-commit via /go2" } else { "${type}: auto-commit via /go2" }

Write-Host "Committing: $msg" -ForegroundColor Cyan
git commit -m $msg
if ($LASTEXITCODE -eq 0) {
    git push origin main
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ DEPLOY SUCCESS" -ForegroundColor Green
    } else {
        Write-Host "X PUSH FAILED" -ForegroundColor Red
        exit 1
    }
}
