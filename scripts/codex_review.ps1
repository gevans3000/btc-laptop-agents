param(
    [string]$OutputPath = ".codex/review.md"
)

$ErrorActionPreference = "Continue"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Resolve-RepoRoot {
    if ($PSScriptRoot) {
        return Split-Path -Parent $PSScriptRoot
    }
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    return Split-Path -Parent $scriptDir
}

function Get-CommandExists([string]$name) {
    return $null -ne (Get-Command $name -ErrorAction SilentlyContinue)
}

function Run-Check([string]$name, [string[]]$command) {
    if (-not (Get-CommandExists $command[0])) {
        return [pscustomobject]@{
            Name = $name
            ExitCode = 127
            Output = "SKIPPED: $($command[0]) not found."
        }
    }

    $output = & $command[0] $command[1..($command.Length - 1)] 2>&1
    $exitCode = $LASTEXITCODE
    return [pscustomobject]@{
        Name = $name
        ExitCode = $exitCode
        Output = $output
    }
}

function Take-Lines([string[]]$lines, [int]$max) {
    if ($lines.Count -le $max) {
        return $lines
    }
    return $lines[0..($max - 1)]
}

$repoRoot = Resolve-RepoRoot
$codexDir = Join-Path $repoRoot ".codex"
New-Item -ItemType Directory -Force -Path $codexDir | Out-Null

$pytestArgs = @("python", "-m", "pytest", "tests/", "-q", "--tb=short", "-p", "no:cacheprovider", "--basetemp=./pytest_temp")
$mypyArgs = @("python", "-m", "mypy", "src/laptop_agents", "--ignore-missing-imports", "--no-error-summary")
$flake8Args = @("python", "-m", "flake8", "src", "tests", "--max-line-length=120", "--ignore=E223,E226,E203,W503")

$checks = @()
$checks += Run-Check "pytest" $pytestArgs
$checks += Run-Check "mypy" $mypyArgs
$checks += Run-Check "flake8" $flake8Args

$failed = $checks | Where-Object { $_.ExitCode -ne 0 -and $_.ExitCode -ne 127 }
$skipped = $checks | Where-Object { $_.ExitCode -eq 127 }

$risk = "low"
if ($failed.Name -contains "pytest") {
    $risk = "high"
} elseif ($failed.Count -gt 0) {
    $risk = "medium"
}

$report = New-Object System.Collections.Generic.List[string]
$report.Add("# Codex Review Report")
$report.Add("")
$report.Add("## Summary")
$report.Add("- Risk: $risk")
$report.Add("- Checks: $($checks.Count) run, $($failed.Count) failed, $($skipped.Count) skipped")
$report.Add("- Generated: $(Get-Date -Format o)")
$report.Add("")
$report.Add("## Prioritized issues")
if ($failed.Count -eq 0) {
    $report.Add("- None detected by automated checks.")
} else {
    $idx = 1
    foreach ($item in $failed) {
        $report.Add("$idx) $($item.Name) failed (exit $($item.ExitCode))")
        $idx++
    }
}

$report.Add("")
$report.Add("## File and line references (first 20 matches per check)")
foreach ($item in $checks) {
    $report.Add("")
    $report.Add("### $($item.Name)")
    $lines = ($item.Output -split "`r?`n") | Where-Object { $_ -match ":\d+" }
    $lines = Take-Lines $lines 20
    if ($lines.Count -eq 0) {
        $report.Add("- None")
    } else {
        foreach ($line in $lines) {
            $report.Add("- $line")
        }
    }
}

$report.Add("")
$report.Add("## Recommended next steps")
if ($failed.Name -contains "pytest") {
    $report.Add("- Run .\\scripts\\codex_fix_loop.ps1 to attempt a fix loop.")
}
if ($failed.Name -contains "mypy") {
    $report.Add("- Address type errors in reported files and re-run mypy.")
}
if ($failed.Name -contains "flake8") {
    $report.Add("- Run black/autoflake/flake8 and re-check lint.")
}
if ($failed.Count -eq 0) {
    $report.Add("- Proceed to pre-PR hardening review if needed.")
}

$outputFullPath = Join-Path $repoRoot $OutputPath
Set-Content -Path $outputFullPath -Value $report -Encoding ASCII
Write-Host "Wrote review report to $outputFullPath"
