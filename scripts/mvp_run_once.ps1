#!/usr/bin/env pwsh
# MVP Run Once - Runs one live tick and opens summary

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

Write-Host "Running one live tick..."

# Run the command
$command = "& '$PSScriptRoot\..\.venv\Scripts\python.exe' -m src.laptop_agents.run --mode live --source mock --symbol BTCUSDT --interval 1m --limit 200"
Invoke-Expression $command

# Open summary.html
$summaryPath = Join-Path -Path $repoRoot -ChildPath "runs\latest\summary.html"
if (Test-Path $summaryPath) {
    Write-Host "Opening summary: $summaryPath"
    Start-Process $summaryPath
} else {
    Write-Host "No summary.html found" -ForegroundColor Yellow
}

Write-Host "Done!"

exit 0