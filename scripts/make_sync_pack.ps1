#!/usr/bin/env pwsh
<#
Assistant Sync Pack Generator
Generates a compact markdown file with project state for AI assistant sync
#>

# Find repo root (where this script lives)
$scriptPath = $PSScriptRoot
$repoRoot = $scriptPath
while (-not (Test-Path -Path "$repoRoot\pyproject.toml")) {
    $repoRoot = Split-Path -Path $repoRoot -Parent
    if ($repoRoot -eq $null) {
        Write-Error "Cannot find repo root (pyproject.toml)"
        exit 1
    }
}

# Ensure runs/latest exists (create if missing)
$runsLatest = Join-Path -Path $repoRoot -ChildPath "runs\latest"
if (-not (Test-Path -Path $runsLatest)) {
    New-Item -ItemType Directory -Path $runsLatest -Force | Out-Null
}

# Get current timestamp
$timestamp = Get-Date -Format "o"  # ISO 8601 format
$timezone = (Get-Date).ToString("zzz")

# Git information
$gitBranch = git rev-parse --abbrev-ref HEAD 2>$null
$gitCommitShort = git rev-parse --short HEAD 2>$null
$gitCommitFull = git rev-parse HEAD 2>$null
$gitStatus = git status --short --branch 2>$null

# Git diff summary
$gitDiffStat = git diff --stat 2>$null

# Key file diffs (truncated if large)
$keyFiles = @(
    "src/laptop_agents/run.py",
    "docs/ASSISTANT_CONTEXT.md", 
    "docs/NEXT.md",
    "scripts/make_sync_pack.ps1"
)

$fileDiffs = @()
foreach ($file in $keyFiles) {
    $fullPath = Join-Path -Path $repoRoot -ChildPath $file
    if (Test-Path -Path $fullPath) {
        $diff = git diff -- "$file" 2>$null
        if ($diff) {
            $lines = $diff -split "`n"
            $truncated = $false
            if ($lines.Count -gt 360) {  # Keep 300 + 60 lines
                $lines = $lines[0..299] + "`n# ... TRUNCATED ...`n" + $lines[($lines.Count-60)..$($lines.Count-1)]
                $truncated = $true
            }
            $fileDiffs += @{
                File = $file
                Diff = $lines -join "`n"
                Truncated = $truncated
            }
        }
    }
}

# Repo structure (depth 2, exclude node_modules/venv)
$treeOutput = tree /F /A $repoRoot | Select-String -Pattern "\\" | Where-Object {
    $_ -notmatch "node_modules" -and 
    $_ -notmatch "\\.venv" -and
    $_ -notmatch "\\.git"
}

# Key file hashes
$filesToHash = @(
    "src/laptop_agents/run.py",
    "pyproject.toml",
    "requirements.txt",
    "docs/ASSISTANT_CONTEXT.md",
    "docs/NEXT.md"
)

$fileHashes = @{}
foreach ($file in $filesToHash) {
    $fullPath = Join-Path -Path $repoRoot -ChildPath $file
    if (Test-Path -Path $fullPath) {
        $hash = (Get-FileHash -Path $fullPath -Algorithm SHA256).Hash
        $fileHashes[$file] = $hash
    }
}

# Last run snapshot
$eventsFile = Join-Path -Path $runsLatest -ChildPath "events.jsonl"
$summaryFile = Join-Path -Path $runsLatest -ChildPath "summary.html"
$tradesFile = Join-Path -Path $runsLatest -ChildPath "trades.csv"

$eventsTail = ""
if (Test-Path -Path $eventsFile) {
    $eventsContent = Get-Content -Path $eventsFile -Tail 60 -ErrorAction SilentlyContinue
    if ($eventsContent) {
        $eventsTail = $eventsContent -join "`n"
    }
}

$summaryInfo = ""
if (Test-Path -Path $summaryFile) {
    $fileInfo = Get-Item -Path $summaryFile
    $summaryInfo = "Size: $($fileInfo.Length) bytes | Modified: $($fileInfo.LastWriteTime)"
}

$tradesSample = ""
if (Test-Path -Path $tradesFile) {
    $tradesContent = Get-Content -Path $tradesFile
    if ($tradesContent.Count -gt 10) {
        $tradesSample = ($tradesContent[0..4] + "...`n" + $tradesContent[($tradesContent.Count-5)..$($tradesContent.Count-1)]) -join "`n"
    } else {
        $tradesSample = $tradesContent -join "`n"
    }
}

# Active "Now" task from NEXT.md
$nextFile = Join-Path -Path $repoRoot -ChildPath "docs/NEXT.md"
$nowTask = ""
if (Test-Path -Path $nextFile) {
    $nextContent = Get-Content -Path $nextFile -Raw
    $nowSection = $nextContent -split "## Next" | Select-Object -First 1
    $nowTask = $nowSection -split "## Now" | Select-Object -Last 1
}

# Generate markdown output using here-string for reliability
$output = @"
# Assistant Sync Pack
Generated: $timestamp ($timezone)

## Git Status

```
Branch: $gitBranch
Commit: $gitCommitShort ($gitCommitFull)
Status: $gitStatus
```

## Git Diff Summary

```
$gitDiffStat
```
"@

if ($fileDiffs.Count -gt 0) {
    $diffsSection = "## Key File Diffs`n"
    foreach ($fileDiff in $fileDiffs) {
        $diffsSection += "`n### $($fileDiff.File)`n`n```diff`n"
        $diffsSection += "$($fileDiff.Diff)`n"
        $diffsSection += "````n"
        if ($fileDiff.Truncated) {
            $diffsSection += "*Diff truncated to first 300 and last 60 lines*`n"
        }
    }
    $diffsSection += "`n"
    $output += $diffsSection
}

$output += @"
## Repo Structure

```
$($treeOutput -join "`n")
```

## Key File Hashes

```
"@

foreach ($file in $filesToHash) {
    if ($fileHashes.ContainsKey($file)) {
        $output += "$file`t$($fileHashes[$file])`n"
    }
}

$output += @"
```

## Last Run Snapshot
"@

if ($summaryInfo) {
    $output += "Summary: $summaryInfo`n`n"
}
if ($eventsTail) {
    $output += @"
Events (last 60 lines):

```json
$eventsTail
```

"@
}
if ($tradesSample) {
    $output += @"
Trades (sample):

```csv
$tradesSample
```

"@
}

if ($nowTask) {
    $output += @"
## Active Now Task

$nowTask

"@
}

# Write output file
$outputFile = Join-Path -Path $repoRoot -ChildPath "assistant_sync_pack.md"
$output | Out-File -FilePath $outputFile -Encoding utf8

Write-Host "Assistant sync pack generated: $outputFile"