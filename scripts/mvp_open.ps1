#!/usr/bin/env pwsh
# MVP Open - Opens the latest summary.html

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Get repository root
$repoRoot = $PSScriptRoot
while (-not (Test-Path -Path (Join-Path $repoRoot "pyproject.toml"))) {
    $repoRoot = Split-Path $repoRoot -Parent
    if ($repoRoot -eq $null) {
        throw "Cannot find repository root (pyproject.toml)"
    }
}

$summaryPath = Join-Path -Path $repoRoot -ChildPath "runs\latest\summary.html"

if (Test-Path $summaryPath) {
    Write-Host "Opening summary: $summaryPath"
    Start-Process $summaryPath
    Write-Host "Summary opened successfully!" -ForegroundColor Green
} else {
    Write-Host "No summary.html found at: $summaryPath" -ForegroundColor Red
    Write-Host "Run a backtest or live session first to generate results." -ForegroundColor Yellow
    exit 1
}

exit 0