<#
.SYNOPSIS
    Local verification script - run this on your laptop before /go2.
.DESCRIPTION
    Performs all verification steps from /go locally, saving AI tokens.
    Outputs verify_report.json for the agent to consume.
.EXAMPLE
    .\.agent\workflows\verify_local.ps1
#>

$ErrorActionPreference = "Continue"
$startTime = Get-Date
$reportPath = ".workspace\verify_report.json"

# Ensure output directory exists
if (-not (Test-Path .workspace)) { New-Item -ItemType Directory -Path .workspace | Out-Null }

$report = @{
    timestamp  = (Get-Date -Format "o")
    git_branch = (git branch --show-current)
    steps      = @{}
    overall    = "pass"
}

function Run-Step {
    param([string]$Name, [scriptblock]$Command)

    Write-Host "`n[$Name]" -ForegroundColor Cyan
    $stepStart = Get-Date

    try {
        & $Command
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            Write-Host "  FAIL (exit $exitCode)" -ForegroundColor Red
            $report.steps[$Name] = @{ status = "fail"; exit_code = $exitCode; duration_s = [math]::Round(((Get-Date) - $stepStart).TotalSeconds, 2) }
            $script:report.overall = "fail"
        }
        else {
            Write-Host "  PASS" -ForegroundColor Green
            $report.steps[$Name] = @{ status = "pass"; duration_s = [math]::Round(((Get-Date) - $stepStart).TotalSeconds, 2) }
        }
    }
    catch {
        Write-Host "  ERROR: $_" -ForegroundColor Red
        $report.steps[$Name] = @{ status = "error"; message = $_.ToString(); duration_s = [math]::Round(((Get-Date) - $stepStart).TotalSeconds, 2) }
        $script:report.overall = "fail"
    }
}

Write-Host "========================================" -ForegroundColor White
Write-Host "  LOCAL VERIFICATION SCRIPT" -ForegroundColor Yellow
Write-Host "  Run this before /go2" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor White

# ─────────────────────────────────────────────────────────────
# STEP 0: Cleanup
# ─────────────────────────────────────────────────────────────
Run-Step "cleanup" {
    if (Test-Path pytest_temp) { Remove-Item -Path pytest_temp -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path local_pytest_temp) { Remove-Item -Path local_pytest_temp -Recurse -Force -ErrorAction SilentlyContinue }
}

# ─────────────────────────────────────────────────────────────
# STEP 1: Format & Lint
# ─────────────────────────────────────────────────────────────
Run-Step "format" {
    python -m ruff format src tests
}

Run-Step "lint" {
    python -m ruff check src tests --fix --extend-ignore=E402
}

# ─────────────────────────────────────────────────────────────
# STEP 2: Syntax & Static Analysis
# ─────────────────────────────────────────────────────────────
Run-Step "compile" {
    python -m compileall src scripts -q
}

Run-Step "doctor" {
    python -m laptop_agents doctor --fix
}

$env:PYTHONPATH = "src"

Run-Step "mypy_general" {
    python -m mypy src/laptop_agents --ignore-missing-imports
}

Run-Step "mypy_strict" {
    python -m mypy src/laptop_agents/core --strict --ignore-missing-imports
}


# ─────────────────────────────────────────────────────────────
# STEP 3: Tests & Coverage
# ─────────────────────────────────────────────────────────────
Run-Step "tests" {
    python -m pytest tests/ -q --tb=short -p no:cacheprovider --cov=laptop_agents --cov-fail-under=50 --cov-branch
}

# ─────────────────────────────────────────────────────────────
# STEP 4: Build
# ─────────────────────────────────────────────────────────────
Run-Step "build" {
    python -m build
}

# ─────────────────────────────────────────────────────────────
# STEP 5: Smoke Test
# ─────────────────────────────────────────────────────────────
Run-Step "smoke" {
    python -m laptop_agents run --mode live-session --duration 1 --source mock --dry-run
}

# ─────────────────────────────────────────────────────────────
# FINALIZE REPORT
# ─────────────────────────────────────────────────────────────
$report.total_duration_s = [math]::Round(((Get-Date) - $startTime).TotalSeconds, 2)
$report.files_changed = @(git diff --name-only)

$report | ConvertTo-Json -Depth 4 | Out-File -FilePath $reportPath -Encoding utf8

Write-Host "`n========================================" -ForegroundColor White
if ($report.overall -eq "pass") {
    Write-Host "  ALL CHECKS PASSED" -ForegroundColor Green
    Write-Host "  Report: $reportPath" -ForegroundColor Gray
    Write-Host "  Next: Run /go2 to commit & push" -ForegroundColor Yellow
}
else {
    Write-Host "  VERIFICATION FAILED" -ForegroundColor Red
    Write-Host "  Report: $reportPath" -ForegroundColor Gray
    Write-Host "  Fix errors above before running /go2" -ForegroundColor Yellow
}
Write-Host "========================================" -ForegroundColor White
