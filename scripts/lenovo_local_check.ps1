<# 
Lenovo Local Check (btc-laptop-agents)
- Runs CI-like checks locally (without pushing)
- Captures logs + a ready-to-paste Codex CLI prompt
- Idempotent: re-runs safely; writes outputs under .workspace\local_check\

Usage:
  powershell -ExecutionPolicy Bypass -File .\scripts\lenovo_local_check.ps1
  powershell -ExecutionPolicy Bypass -File .\scripts\lenovo_local_check.ps1 -Quick
  powershell -ExecutionPolicy Bypass -File .\scripts\lenovo_local_check.ps1 -NoInstall
  powershell -ExecutionPolicy Bypass -File .\scripts\lenovo_local_check.ps1 -IncludeStress
#>

param(
  [switch]$Quick,
  [switch]$NoInstall,
  [switch]$IncludeStress,
  [switch]$SkipSmoke,
  [int]$Retries = 2,
  [int]$PipTimeoutSec = 120
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function NowStamp { Get-Date -Format "yyyyMMdd-HHmmss" }

function Ensure-Dir([string]$p) {
  if (-not (Test-Path $p)) { New-Item -ItemType Directory -Force $p | Out-Null }
}

function Run-Step {
  param(
    [string]$Name,
    [scriptblock]$Cmd,
    [string]$LogPath
  )
  $start = Get-Date
  $rc = 0
  $out = ""
  $prevEap = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    $out = & $Cmd 2>&1 | Out-String
    $rc = $LASTEXITCODE
    if ($null -eq $rc) { $rc = 0 }
  } catch {
    $out = ($_ | Out-String)
    $rc = 1
  } finally {
    $ErrorActionPreference = $prevEap
  }
  $elapsed = (Get-Date) - $start
  Add-Content -Path $LogPath -Value ("`n--- STEP: {0}`nRC: {1}`nElapsed: {2}`nCMD_OUT:`n{3}" -f $Name, $rc, $elapsed, $out)
  return [pscustomobject]@{ name=$Name; rc=$rc; elapsed=$elapsed; log=$LogPath; tail=($out -split "`n" | Select-Object -Last 30) -join "`n" }
}

function Find-RepoRoot {
  try {
    $root = (git rev-parse --show-toplevel 2>$null).Trim()
    if (-not $root) { throw "Not a git repo" }
    return $root
  } catch {
    throw "Run this from inside the btc-laptop-agents repo (git required)."
  }
}

function Pick-Python {
  # Prefer existing venv python
  if (Test-Path ".\.venv\Scripts\python.exe") { return ".\.venv\Scripts\python.exe" }
  # Prefer py launcher if available
  if (Get-Command py -ErrorAction SilentlyContinue) { return "py" }
  if (Get-Command python -ErrorAction SilentlyContinue) { return "python" }
  throw "Python not found (need py or python)."
}

function Ensure-Venv([string]$BasePy) {
  if (Test-Path ".\.venv\Scripts\python.exe") { return ".\.venv\Scripts\python.exe" }

  Write-Host "Creating venv at .\.venv ..."
  if ($BasePy -eq "py") {
    # Try 3.11 first, then default
    & py -3.11 -m venv .venv 2>$null
    if ($LASTEXITCODE -ne 0) { & py -m venv .venv }
  } else {
    & $BasePy -m venv .venv
  }
  if (-not (Test-Path ".\.venv\Scripts\python.exe")) { throw "Failed to create venv." }
  return ".\.venv\Scripts\python.exe"
}

function Get-LaPath {
  if (Test-Path ".\.venv\Scripts\la.exe") { return ".\.venv\Scripts\la.exe" }
  return $null
}

# --- Main ---
$repoRoot = Find-RepoRoot
Set-Location $repoRoot

$stamp = NowStamp
$outDir = Join-Path $repoRoot ".workspace\local_check\$stamp"
Ensure-Dir $outDir
$logPath = Join-Path $outDir "local_check.log"

Add-Content $logPath "Lenovo Local Check - $stamp"
Add-Content $logPath ("Repo: {0}" -f $repoRoot)

# Basic machine + repo info (no secrets)
$computer = $env:COMPUTERNAME
Add-Content $logPath ("Computer: {0}" -f $computer)
Add-Content $logPath ("OS: {0}" -f (Get-CimInstance Win32_OperatingSystem | Select-Object -ExpandProperty Caption))
Add-Content $logPath ("Git HEAD: {0}" -f ((git rev-parse HEAD).Trim()))
Add-Content $logPath ("Git branch: {0}" -f ((git branch --show-current).Trim()))
Add-Content $logPath ("Git status: {0}" -f ((git status --porcelain | Out-String).Trim()))

# Local temp/cache dirs to avoid Windows ACL weirdness
$localTmp = Join-Path $repoRoot ".tmp"
$localCache = Join-Path $repoRoot ".pip-cache"
Ensure-Dir $localTmp
Ensure-Dir $localCache
$env:TMP = $localTmp
$env:TEMP = $localTmp
$env:TMPDIR = $localTmp
$env:PIP_CACHE_DIR = $localCache

$basePy = Pick-Python
$py = Ensure-Venv $basePy
$la = Get-LaPath

# pip timeout/retry args
$pipArgs = @("--default-timeout", "$PipTimeoutSec", "--retries", "$Retries")

$results = @()

# --- Install / tooling (best effort) ---
if (-not $NoInstall) {
  $results += Run-Step "pip_upgrade" { & $py -m pip install --upgrade pip setuptools wheel @pipArgs } $logPath
  $results += Run-Step "pip_check_pre" { & $py -m pip check } $logPath
  $results += Run-Step "install_editable_test" { & $py -m pip install -e ".[test]" @pipArgs } $logPath
  $results += Run-Step "install_ci_tools" { & $py -m pip install build mypy pip-audit @pipArgs } $logPath
} else {
  Add-Content $logPath "`n--- NOTE: -NoInstall specified; skipping installs."
}

# Refresh la path after install
$la = Get-LaPath

# --- CI-like checks (avoid long work if -Quick) ---
# Set CI env to mirror CI behavior (e.g., stress tests skipped if they check CI)
$prevCI = $env:CI
$env:CI = "true"

$buildArgs = @("--no-isolation")

$results += Run-Step "import_check" { & $py -c "import laptop_agents; print('ok')" } $logPath
$prevPythonPath = $env:PYTHONPATH
if ($prevPythonPath) {
  $env:PYTHONPATH = "$repoRoot\\scripts;$prevPythonPath"
} else {
  $env:PYTHONPATH = "$repoRoot\\scripts"
}
$results += Run-Step "build" { & $py -m build @buildArgs } $logPath
if ($null -eq $prevPythonPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue } else { $env:PYTHONPATH = $prevPythonPath }
$results += Run-Step "compileall" { & $py -m compileall src } $logPath

if ($Quick) {
  $results += Run-Step "pytest_quick" { & $py -m pytest -q --tb=short --maxfail=1 } $logPath
} else {
  $results += Run-Step "pytest" { & $py -m pytest -q --tb=short } $logPath
}

$results += Run-Step "mypy" { & $py -m mypy src/laptop_agents --ignore-missing-imports --no-error-summary } $logPath
$results += Run-Step "pip_audit" { & $py -m pip_audit --dry-run --cache-dir $localCache } $logPath

if ($la) {
  $results += Run-Step "la_help" { & $la --help } $logPath
  if (-not $SkipSmoke) {
    $results += Run-Step "la_doctor" { & $la doctor --fix } $logPath
  } else {
    Add-Content $logPath "`n--- NOTE: -SkipSmoke specified; skipping la doctor."
  }
} else {
  Add-Content $logPath "`n--- NOTE: la.exe not found in venv; skipping la checks."
}

# restore CI env
if ($null -eq $prevCI) { Remove-Item Env:CI -ErrorAction SilentlyContinue } else { $env:CI = $prevCI }

# Optional: run stress tests intentionally (separate; can be long)
if ($IncludeStress) {
  Add-Content $logPath "`n--- STRESS RUN (requested): tests/stress"
  $results += Run-Step "pytest_stress" { & $py -m pytest -q tests/stress --tb=short } $logPath
}

# --- Summarize results ---
$fail = $results | Where-Object { $_.rc -ne 0 }
$summaryPath = Join-Path $outDir "summary.md"

$summary = @()
$summary += "# Local Check Summary ($stamp)"
$summary += ""
$summary += "- Repo: $repoRoot"
$summary += "- Branch: $((git branch --show-current).Trim())"
$summary += "- HEAD: $((git rev-parse HEAD).Trim())"
$summary += "- Python: $(& $py --version 2>&1)"
$summary += "- Venv Python: $py"
$summary += "- Log: $logPath"
$summary += ""

$summary += "## Step Results"
foreach ($r in $results) {
  $summary += ("- {0}: rc={1} ({2})" -f $r.name, $r.rc, $r.elapsed)
}
$summary += ""

if ($fail.Count -eq 0) {
  $summary += "âœ… All local checks passed."
} else {
  $summary += "âŒ Failures:"
  foreach ($f in $fail) {
    $summary += ("- {0} (rc={1})" -f $f.name, $f.rc)
  }
  $summary += ""
  $summary += "### Failure tails (last ~30 lines per failing step)"
  foreach ($f in $fail) {
    $summary += ""
    $summary += "#### $($f.name)"
    $summary += '`'
    $summary += $f.tail
    $summary += '`'
  }
}

Set-Content -Path $summaryPath -Value ($summary -join "`n") -Encoding UTF8

# --- Generate Codex prompt (ready to paste) ---
$promptPath = Join-Path $outDir "codex_prompt.txt"

$codex = @()
$codex += "You are Codex 5.2 running autonomously inside gevans3000/btc-laptop-agents with shell access."
$codex += ""
$codex += "TASK"
$codex += "- Fix whatever caused the failing local CI-like checks, using minimal diffs and small commits."
$codex += "- Do NOT change product behavior. Preserve invariants: BTCUSDT default/normalization, .workspace/, LA_* precedence, no live enablement, state persistence."
$codex += "- Do NOT commit secrets/artifacts (.env, .workspace, logs, temp dirs)."
$codex += "- Re-run ONLY the failing step(s) to verify fixes (not the full suite)."
$codex += ""
$codex += "LOCAL ENV CONTEXT"
$codex += "- Branch: $((git branch --show-current).Trim())"
$codex += "- HEAD: $((git rev-parse HEAD).Trim())"
$codex += "- Python: $(& $py --version 2>&1)"
$codex += "- Venv python: $py"
$codex += "- Primary log: $logPath"
$codex += "- Summary: $summaryPath"
$codex += ""
$codex += "FAILURES"
if ($fail.Count -eq 0) {
  $codex += "- None. If CI still fails, fetch GH Actions failing logs and fix based on those."
} else {
  foreach ($f in $fail) {
    $codex += ("- {0} (rc={1})  see log section in: {2}" -f $f.name, $f.rc, $logPath)
  }
}
$codex += ""
$codex += "INSTRUCTIONS"
$codex += "1) Open the summary + log files above and identify the FIRST failing step."
$codex += "2) Fix the root cause with the smallest safe change."
$codex += "3) Re-run only that failing command to verify."
$codex += "4) Commit with Conventional Commit format and body: Cause/Change/Verification."
$codex += "5) Repeat until failures are resolved."
$codex += ""
$codex += "MINIMAL COMMANDS (use venv python)"
$codex += "- $py -m build"
$codex += "- $py -m compileall src"
$codex += "- $py -m pytest -q --tb=short --maxfail=1"
$codex += "- $py -m mypy src/laptop_agents --ignore-missing-imports --no-error-summary"
$codex += "- $py -m pip_audit"
$codex += "- .\.venv\Scripts\la.exe --help"
$codex += ""
$codex += "STOP when local failures are gone (or clearly explained), with clean git status."
Set-Content -Path $promptPath -Value ($codex -join "`n") -Encoding UTF8

Write-Host ""
Write-Host "DONE."
Write-Host "Summary: $summaryPath"
Write-Host "Codex prompt: $promptPath"
Write-Host ""
Write-Host "TIP: Open the prompt file and paste it into Codex CLI:"
Write-Host "  notepad $promptPath"

