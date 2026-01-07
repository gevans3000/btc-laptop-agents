#!/usr/bin/env pwsh
# Comprehensive verification script for btc-laptop-agents
# Tests compilation, selftest, and basic functionality

param (
    [string]$Mode = "full",  # full, quick, or selftest-only
    [string]$IntrabarMode = "conservative"  # conservative or optimistic
)

# Set strict mode for better error handling
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Function to run command and capture output
function Run-CommandWithOutput {
    param (
        [string]$Command,
        [string]$WorkingDirectory = $PWD
    )
    
    Write-Host "Running: $Command"
    
    $result = Invoke-Expression -Command $Command -ErrorAction Stop
    return $result
}

# Function to run command and check success
function Run-CommandCheck {
    param (
        [string]$Command,
        [string]$WorkingDirectory = $PWD,
        [string]$SuccessMessage,
        [string]$FailureMessage
    )
    
    try {
        $output = Run-CommandWithOutput -Command $Command -WorkingDirectory $WorkingDirectory
        Write-Host "✓ $SuccessMessage"
        return $true
    } catch {
        Write-Host "✗ $FailureMessage"
        Write-Host "Error: $_"
        return $false
    }
}

# Get repository root
$repoRoot = $PSScriptRoot
while (-not (Test-Path -Path (Join-Path $repoRoot "pyproject.toml"))) {
    $repoRoot = Split-Path $repoRoot -Parent
    if ($repoRoot -eq $null) {
        throw "Cannot find repository root (pyproject.toml)"
    }
}

Write-Host "Repository root: $repoRoot"

# Change to repository root
Set-Location $repoRoot

$allPassed = $true

# 1. Compilation test
if ($Mode -ne "selftest-only") {
    Write-Host ""
    Write-Host "=== COMPILATION TEST ==="
    
    $compilationPassed = Run-CommandCheck -Command "python -m compileall src" -SuccessMessage "Compilation successful" -FailureMessage "Compilation failed"
    $allPassed = $allPassed -and $compilationPassed
}

# 2. Selftest - Conservative mode
Write-Host ""
Write-Host "=== SELFTEST - CONSERVATIVE MODE ==="

$selftestConservativePassed = Run-CommandCheck -Command "python -m src.laptop_agents.run --mode selftest --intrabar-mode conservative" -SuccessMessage "Selftest (conservative) passed" -FailureMessage "Selftest (conservative) failed"
$allPassed = $allPassed -and $selftestConservativePassed

# 3. Selftest - Optimistic mode
Write-Host ""
Write-Host "=== SELFTEST - OPTIMISTIC MODE ==="

$selftestOptimisticPassed = Run-CommandCheck -Command "python -m src.laptop_agents.run --mode selftest --intrabar-mode optimistic" -SuccessMessage "Selftest (optimistic) passed" -FailureMessage "Selftest (optimistic) failed"
$allPassed = $allPassed -and $selftestOptimisticPassed

# 4. Mock backtest test (if full mode)
if ($Mode -eq "full") {
    Write-Host ""
    Write-Host "=== MOCK BACKTEST TEST ==="
    
    $backtestPassed = Run-CommandCheck -Command "python -m src.laptop_agents.run --mode backtest --source mock --limit 500 --backtest 500" -SuccessMessage "Mock backtest completed successfully" -FailureMessage "Mock backtest failed"
    $allPassed = $allPassed -and $backtestPassed
    
    # Check that summary.html was created
    $summaryPath = Join-Path $repoRoot "runs" "latest" "summary.html"
    if (Test-Path $summaryPath) {
        Write-Host "✓ summary.html created successfully"
        # Open the summary in default browser
        Start-Process $summaryPath -ErrorAction SilentlyContinue
    } else {
        Write-Host "✗ summary.html not found"
        $allPassed = $false
    }
}

# Final result
Write-Host ""
Write-Host "=== VERIFICATION RESULTS ==="

if ($allPassed) {
    Write-Host "VERIFY: PASS - All tests passed successfully!"
    exit 0
} else {
    Write-Host "VERIFY: FAIL - Some tests failed"
    exit 1
}

# Usage examples:
# Full verification: .\scripts\verify.ps1 -Mode full
# Quick verification: .\scripts\verify.ps1 -Mode quick
# Selftest only: .\scripts\verify.ps1 -Mode selftest-only