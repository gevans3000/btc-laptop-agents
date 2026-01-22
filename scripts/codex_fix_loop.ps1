param(
    [int]$MaxIterations = 3,
    [string]$ReportPath = ".codex/fix-report.md",
    [switch]$AutoApprove
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

function Run-Tests {
    $output = & python -m pytest tests/ -q --tb=short -p no:cacheprovider --basetemp=./pytest_temp 2>&1
    $exitCode = $LASTEXITCODE
    return [pscustomobject]@{
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

$report = New-Object System.Collections.Generic.List[string]
$report.Add("# Codex Fix Loop Report")
$report.Add("")
$report.Add("## Summary")
$report.Add("- Max iterations: $MaxIterations")
$report.Add("- Generated: $(Get-Date -Format o)")
$report.Add("")

$fixCmd = $env:CODEX_FIX_CMD
$codexCmd = Get-Command codex.cmd -ErrorAction SilentlyContinue
$promptPath = Join-Path $repoRoot ".agent/workflows/fix.md"
$useCodexPrompt = (-not $fixCmd) -and $null -ne $codexCmd -and (Test-Path $promptPath)

$status = "blocked"
$autoApprove = $AutoApprove -or ($env:CODEX_FIX_AUTO_APPROVE -in @("1", "true", "True", "YES", "yes"))
for ($i = 1; $i -le $MaxIterations; $i++) {
    $report.Add("## Iteration $i")
    $testResult = Run-Tests
    $report.Add("- Test exit code: $($testResult.ExitCode)")

    $testLines = Take-Lines ($testResult.Output -split "`r?`n") 200
    $report.Add("")
    $report.Add('```')
    foreach ($line in $testLines) {
        $report.Add($line)
    }
    $report.Add('```')
    $report.Add("")

    if ($testResult.ExitCode -eq 0) {
        $status = "success"
        $report.Add("- Status: tests green.")
        break
    }

    if (-not $fixCmd -and -not $useCodexPrompt) {
        $report.Add("- Status: blocked (no CODEX_FIX_CMD and codex.cmd not found).")
        break
    }

    if (-not $autoApprove) {
        $confirm = Read-Host "Tests failed. Run fix command? (y/N)"
        if ($confirm -ne "y" -and $confirm -ne "Y") {
            $report.Add("- Status: blocked (user declined fix command).")
            break
        }
    } else {
        $report.Add("- Auto-approve enabled; running fix command.")
    }

    if ($useCodexPrompt) {
        $report.Add("- Running Codex fix workflow via codex.cmd.")
        $prompt = Get-Content $promptPath -Raw
        $prompt | & $codexCmd.Source exec -
    } else {
        $report.Add("- Running fix command: $fixCmd")
        Invoke-Expression $fixCmd
    }
    $report.Add("- Fix command completed.")
    $report.Add("")
}

$report.Add("")
$report.Add("## Final status")
$report.Add("- $status")

if ($status -ne "success") {
    $report.Add("")
    $report.Add("## Recommended next steps")
    $report.Add("- Inspect failing test output and address the first failure.")
    $report.Add("- Re-run .\\scripts\\codex_fix_loop.ps1 after fixes.")
}

$outputFullPath = Join-Path $repoRoot $ReportPath
Set-Content -Path $outputFullPath -Value $report -Encoding ASCII
Write-Host "Wrote fix loop report to $outputFullPath"
