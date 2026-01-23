<#
Lenovo Local Check (btc-laptop-agents)
- Runs CI-like checks locally (no prompts).
- Uses safe LocalAppData temp to avoid Windows ACL issues.
- Captures logs + summary + Codex prompt under .workspace\local_check\<timestamp>\.

Usage:
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\lenovo_local_check.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\lenovo_local_check.ps1 -Quick
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\lenovo_local_check.ps1 -NoInstall
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\lenovo_local_check.ps1 -SkipSmoke
  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\lenovo_local_check.ps1 -IncludeStress
#>

param(
  [switch]$Quick,
  [switch]$NoInstall,
  [switch]$IncludeStress,
  [switch]$SkipSmoke
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function NowStamp { Get-Date -Format "yyyyMMdd-HHmmss" }

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path $Path)) { New-Item -ItemType Directory -Force -Path $Path | Out-Null }
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

function Write-Log([string]$LogPath, [string]$Message) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Path $LogPath -Value ("[{0}] {1}" -f $ts, $Message)
}

function Invoke-Step {
  param(
    [string]$Name,
    [string]$Command,
    [scriptblock]$Action,
    [string]$LogPath,
    [string]$StatusOnSkip = "SKIP"
  )
  $start = Get-Date
  Write-Log $LogPath ("STEP {0} START {1}" -f $Name, $start)
  Write-Log $LogPath ("CMD: {0}" -f $Command)
  $rc = 0
  $out = ""
  $prevEap = $ErrorActionPreference
  try {
    $ErrorActionPreference = "Continue"
    $out = & $Action 2>&1 | Out-String
    $rc = $LASTEXITCODE
    if ($null -eq $rc) { $rc = 0 }
  } catch {
    $out = ($_ | Out-String)
    $rc = 1
  } finally {
    $ErrorActionPreference = $prevEap
  }
  $end = Get-Date
  $tail = ($out -split "`r?`n" | Select-Object -Last 40) -join "`n"
  Write-Log $LogPath ("STEP {0} END {1} RC={2}" -f $Name, $end, $rc)
  Write-Log $LogPath "OUTPUT_START"
  if ($out) { Add-Content -Path $LogPath -Value $out }
  Write-Log $LogPath "OUTPUT_END"
  $status = if ($rc -eq 0) { "PASS" } else { "FAIL" }
  return [pscustomobject]@{
    name = $Name
    command = $Command
    start = $start
    end = $end
    rc = $rc
    status = $status
    tail = $tail
  }
}

function New-SkipResult {
  param(
    [string]$Name,
    [string]$Reason,
    [string]$Command,
    [string]$LogPath
  )
  Write-Log $LogPath ("STEP {0} SKIP {1}" -f $Name, $Reason)
  return [pscustomobject]@{
    name = $Name
    command = $Command
    start = $null
    end = $null
    rc = 0
    status = "SKIP"
    tail = $Reason
  }
}

function Test-Online {
  try {
    $tnc = Test-NetConnection -ComputerName "pypi.org" -Port 443 -InformationLevel Quiet -WarningAction SilentlyContinue -ErrorAction SilentlyContinue
    if ($tnc) { return $true }
  } catch {
    # ignore
  }
  try {
    $dns = Resolve-DnsName "pypi.org" -ErrorAction SilentlyContinue
    if ($dns) { return $true }
  } catch {
    # ignore
  }
  return $false
}

function Pick-Python {
  if (Test-Path ".\\.venv\\Scripts\\python.exe") { return ".\\.venv\\Scripts\\python.exe" }
  if (Get-Command py -ErrorAction SilentlyContinue) { return "py" }
  if (Get-Command python -ErrorAction SilentlyContinue) { return "python" }
  throw "Python not found (need py or python)."
}

function Ensure-Venv([string]$BasePy) {
  if (Test-Path ".\\.venv\\Scripts\\python.exe") { return ".\\.venv\\Scripts\\python.exe" }
  Write-Host "Creating venv at .\\.venv ..."
  if ($BasePy -eq "py") {
    & py -3.11 -m venv .venv 2>$null
    if ($LASTEXITCODE -ne 0) { & py -m venv .venv }
  } else {
    & $BasePy -m venv .venv
  }
  if (-not (Test-Path ".\\.venv\\Scripts\\python.exe")) { throw "Failed to create venv." }
  return ".\\.venv\\Scripts\\python.exe"
}

function Get-LaPath {
  if (Test-Path ".\\.venv\\Scripts\\la.exe") { return ".\\.venv\\Scripts\\la.exe" }
  return $null
}

function Is-TempAclError([string]$Text) {
  if (-not $Text) { return $false }
  $patterns = @(
    "Access is denied",
    "PermissionError",
    "WinError 5",
    "WinError 32",
    "WinError 267",
    "[Errno 13]",
    "Operation not permitted",
    "The system cannot find the path",
    "No such file or directory",
    "Temporary",
    "temp"
  )
  foreach ($p in $patterns) {
    if ($Text -match [regex]::Escape($p)) { return $true }
  }
  return $false
}

function Invoke-BuildStep {
  param(
    [string]$Name,
    [string]$LogPath,
    [string]$Py,
    [bool]$IsOnline,
    [string]$RunId
  )
  $start = Get-Date
  $command = "$Py -m build (isolated; retry once; fallback to --no-isolation if offline/ACL)"
  Write-Log $LogPath ("STEP {0} START {1}" -f $Name, $start)
  Write-Log $LogPath ("CMD: {0}" -f $command)

  $outAll = ""
  $rcFinal = 1

  $run = {
    param([string]$Label, [string[]]$Args)
    Write-Log $LogPath ("ATTEMPT {0}: {1} {2}" -f $Label, $Py, ($Args -join " "))
    $out = & $Py @Args 2>&1 | Out-String
    $rc = $LASTEXITCODE
    if ($null -eq $rc) { $rc = 0 }
    $outAll += ("`n--- {0} OUTPUT ---`n{1}" -f $Label, $out)
    return [pscustomobject]@{ rc = $rc; out = $out }
  }

  $first = & $run "isolated" @("-m","build")
  if ($first.rc -eq 0) {
    $rcFinal = 0
  } else {
    . "$PSScriptRoot\\set_safe_temp.ps1" -RunId ("{0}-retry1" -f $RunId)
    $second = & $run "isolated_retry" @("-m","build")
    if ($second.rc -eq 0) {
      $rcFinal = 0
    } else {
      $aclOrTemp = Is-TempAclError ($first.out + $second.out)
      if (-not $IsOnline -or $aclOrTemp) {
        $third = & $run "no_isolation_fallback" @("-m","build","--no-isolation")
        $rcFinal = $third.rc
      } else {
        $rcFinal = $second.rc
      }
    }
  }

  $end = Get-Date
  $tail = ($outAll -split "`r?`n" | Select-Object -Last 40) -join "`n"
  Write-Log $LogPath ("STEP {0} END {1} RC={2}" -f $Name, $end, $rcFinal)
  Write-Log $LogPath "OUTPUT_START"
  if ($outAll) { Add-Content -Path $LogPath -Value $outAll }
  Write-Log $LogPath "OUTPUT_END"

  $status = if ($rcFinal -eq 0) { "PASS" } else { "FAIL" }
  return [pscustomobject]@{
    name = $Name
    command = $command
    start = $start
    end = $end
    rc = $rcFinal
    status = $status
    tail = $tail
  }
}

# --- Main ---
$repoRoot = Find-RepoRoot
Set-Location $repoRoot

$stamp = NowStamp
$outDir = Join-Path $repoRoot ".workspace\\local_check\\$stamp"
Ensure-Dir $outDir
$logPath = Join-Path $outDir "local_check.log"

Write-Log $logPath ("Lenovo Local Check - {0}" -f $stamp)
Write-Log $logPath ("Repo: {0}" -f $repoRoot)
Write-Log $logPath ("Computer: {0}" -f $env:COMPUTERNAME)
try {
  $osCaption = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop | Select-Object -ExpandProperty Caption
} catch {
  $osCaption = "Unknown (CIM access denied)"
}
Write-Log $logPath ("OS: {0}" -f $osCaption)
Write-Log $logPath ("Git HEAD: {0}" -f ((git rev-parse HEAD).Trim()))
Write-Log $logPath ("Git branch: {0}" -f ((git branch --show-current).Trim()))
Write-Log $logPath ("Git status: {0}" -f ((git status --porcelain | Out-String).Trim()))

# Safe temp
. "$PSScriptRoot\\set_safe_temp.ps1" -RunId $stamp

$pytestBaseTemp = Join-Path $repoRoot ".workspace\\pytest_temp\\$stamp"
Ensure-Dir $pytestBaseTemp

$basePy = Pick-Python
$py = Ensure-Venv $basePy
$la = Get-LaPath

$isOnline = Test-Online
Write-Log $logPath ("Online: {0}" -f $isOnline)

$results = @()

# Command strings (avoid escaping issues)
$cmdPipUpgrade = "{0} -m pip install --upgrade pip setuptools wheel" -f $py
$cmdPipCheck = "{0} -m pip check" -f $py
$cmdInstallEditable = "{0} -m pip install -e "".[test]""" -f $py
$cmdInstallTools = "{0} -m pip install build mypy pip-audit" -f $py
$cmdImportCheck = "{0} -c ""import laptop_agents; print(''ok'')""" -f $py
$cmdCompileAll = "{0} -m compileall src" -f $py
$cmdMypy = "{0} -m mypy src/laptop_agents --ignore-missing-imports --no-error-summary" -f $py
$cmdPipAudit = "{0} -m pip_audit" -f $py
$cmdLaHelp = ".\\.venv\\Scripts\\la.exe --help"
$cmdLaDoctor = ".\\.venv\\Scripts\\la.exe doctor --fix"
$cmdSmokeRun = "{0} -m laptop_agents run --mode live-session --duration 1 --symbol BTCUSDT --source mock --execution-mode paper --dry-run --async" -f $py

# 1) pip upgrade (best-effort)
$results += Invoke-Step "pip_upgrade" $cmdPipUpgrade { & $py -m pip install --upgrade pip setuptools wheel } $logPath

# 2) pip check (best-effort)
$results += Invoke-Step "pip_check" $cmdPipCheck { & $py -m pip check } $logPath

# 3) install -e ".[test]" (unless -NoInstall)
if (-not $NoInstall) {
  $results += Invoke-Step "install_editable_test" $cmdInstallEditable { & $py -m pip install -e ".[test]" } $logPath
} else {
  $results += New-SkipResult "install_editable_test" "Skipped by -NoInstall" $cmdInstallEditable $logPath
}

# 4) install build/mypy/pip-audit (unless -NoInstall)
if (-not $NoInstall) {
  $results += Invoke-Step "install_ci_tools" $cmdInstallTools { & $py -m pip install build mypy pip-audit } $logPath
} else {
  $results += New-SkipResult "install_ci_tools" "Skipped by -NoInstall" $cmdInstallTools $logPath
}

# Refresh la path after installs
$la = Get-LaPath

# 5) import_check
$results += Invoke-Step "import_check" $cmdImportCheck { & $py -c "import laptop_agents; print('ok')" } $logPath

# 6) build (prefer isolated; retry once after refreshing temp; fallback to --no-isolation only if offline or ACL/temp error)
$results += Invoke-BuildStep "build" $logPath $py $isOnline $stamp

# 7) compileall
$results += Invoke-Step "compileall" $cmdCompileAll { & $py -m compileall src } $logPath

# 8) pytest_core (exclude tests/stress; basetemp; disable cacheprovider; -Quick adds --maxfail=1)
$pytestArgs = @("-m","pytest","-q","--tb=short","--basetemp",$pytestBaseTemp,"-p","no:cacheprovider","--ignore=tests/stress")
if ($Quick) { $pytestArgs += @("--maxfail=1") }
$results += Invoke-Step "pytest_core" "$py $($pytestArgs -join ' ')" { & $py @pytestArgs } $logPath

# 9) mypy
$results += Invoke-Step "mypy" $cmdMypy { & $py -m mypy src/laptop_agents --ignore-missing-imports --no-error-summary } $logPath

# 10) pip-audit (only if online)
if ($isOnline) {
  $results += Invoke-Step "pip_audit" $cmdPipAudit { & $py -m pip_audit } $logPath
} else {
  $results += New-SkipResult "pip_audit" "Offline; skipped" $cmdPipAudit $logPath
}

# 11) la --help
if ($la) {
  $results += Invoke-Step "la_help" $cmdLaHelp { & $la --help } $logPath
} else {
  $results += New-SkipResult "la_help" "la.exe not found in .venv" $cmdLaHelp $logPath
}

# 12) smoke (unless -SkipSmoke)
if (-not $SkipSmoke) {
  if ($la) {
    $results += Invoke-Step "la_doctor_fix" $cmdLaDoctor { & $la doctor --fix } $logPath
  } else {
    $results += New-SkipResult "la_doctor_fix" "la.exe not found in .venv" $cmdLaDoctor $logPath
  }
  $results += Invoke-Step "smoke_run" $cmdSmokeRun { & $py -m laptop_agents run --mode live-session --duration 1 --symbol BTCUSDT --source mock --execution-mode paper --dry-run --async } $logPath
} else {
  $results += New-SkipResult "la_doctor_fix" "Skipped by -SkipSmoke" $cmdLaDoctor $logPath
  $results += New-SkipResult "smoke_run" "Skipped by -SkipSmoke" $cmdSmokeRun $logPath
}

# 13) optional stress
if ($IncludeStress) {
  $stressArgs = @("-m","pytest","-q","--tb=short","--basetemp",$pytestBaseTemp,"-p","no:cacheprovider","tests/stress")
  $results += Invoke-Step "pytest_stress" "$py $($stressArgs -join ' ')" { & $py @stressArgs } $logPath
}

# --- Summary ---
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
$summary += "| Step | Status | RC | Duration | Command |"
$summary += "| --- | --- | --- | --- | --- |"
foreach ($r in $results) {
  $dur = if ($r.start -and $r.end) { "{0:n1}s" -f (($r.end - $r.start).TotalSeconds) } else { "-" }
  $summary += ("| {0} | {1} | {2} | {3} | {4} |" -f $r.name, $r.status, $r.rc, $dur, $r.command)
}
$summary += ""

$failures = $results | Where-Object { $_.status -eq "FAIL" }
if ($failures.Count -eq 0) {
  $summary += "All local checks passed."
} else {
  $summary += "Failures:"
  foreach ($f in $failures) {
    $summary += ("- {0} (rc={1})" -f $f.name, $f.rc)
  }
  $summary += ""
  $summary += "## Failure tails"
  foreach ($f in $failures) {
    $summary += ""
    $summary += ("### {0}" -f $f.name)
    $summary += '```'
    $summary += $f.tail
    $summary += '```'
  }
}

Set-Content -Path $summaryPath -Value ($summary -join "`n") -Encoding UTF8

# --- Codex prompt ---
$promptPath = Join-Path $outDir "codex_prompt.txt"

$minimalCommands = @{
  "pip_upgrade" = $cmdPipUpgrade
  "pip_check" = $cmdPipCheck
  "install_editable_test" = $cmdInstallEditable
  "install_ci_tools" = $cmdInstallTools
  "import_check" = $cmdImportCheck
  "build" = "$py -m build"
  "compileall" = $cmdCompileAll
  "pytest_core" = "$py -m pytest -q --tb=short --basetemp $pytestBaseTemp -p no:cacheprovider --ignore=tests/stress"
  "mypy" = $cmdMypy
  "pip_audit" = $cmdPipAudit
  "la_help" = $cmdLaHelp
  "la_doctor_fix" = $cmdLaDoctor
  "smoke_run" = $cmdSmokeRun
  "pytest_stress" = "$py -m pytest -q --tb=short --basetemp $pytestBaseTemp -p no:cacheprovider tests/stress"
}

$codex = @()
$codex += "You are Codex 5.2 running autonomously inside gevans3000/btc-laptop-agents with shell access."
$codex += ""
$codex += "PATHS"
$codex += "- Summary: $summaryPath"
$codex += "- Log: $logPath"
$codex += ""
$codex += "SAFE TEMP (run first in the same shell)"
$codex += '```powershell'
$codex += "powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\set_safe_temp.ps1 -RunId $stamp-rerun"
$codex += '```'
$codex += ""
$codex += "FAILURES"
if ($failures.Count -eq 0) {
  $codex += "- None."
} else {
  foreach ($f in $failures) {
    $codex += ("- {0} (rc={1})" -f $f.name, $f.rc)
  }
}
$codex += ""
$codex += "MINIMAL RERUN COMMANDS (only failing steps)"
if ($failures.Count -eq 0) {
  $codex += "- None."
} else {
  foreach ($f in $failures) {
    if ($minimalCommands.ContainsKey($f.name)) {
      $codex += ("- {0}" -f $minimalCommands[$f.name])
    } else {
      $codex += ("- (no command mapping for step: {0})" -f $f.name)
    }
  }
}
$codex += ""
$codex += "INSTRUCTIONS"
$codex += "1) Open summary + log, identify the first failing step."
$codex += "2) Fix the root cause with the smallest safe change."
$codex += "3) Re-run only that failing command to verify."
$codex += "4) Commit small, then repeat until failures are resolved."

Set-Content -Path $promptPath -Value ($codex -join "`n") -Encoding UTF8

Write-Host ""
Write-Host "DONE."
Write-Host "Summary: $summaryPath"
Write-Host "Codex prompt: $promptPath"
