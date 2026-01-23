<#
Set safe temp/cache dirs for local checks.
- Sets TMP/TEMP/TMPDIR/PIP_CACHE_DIR to LocalAppData\Temp\btc_laptop_agents_local_check\<RunId>\
- Creates directories and prints chosen paths.
- Idempotent and non-interactive.
#>

param(
  [string]$RunId = (Get-Date -Format "yyyyMMdd-HHmmss")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $env:LOCALAPPDATA) {
  throw "LOCALAPPDATA is not set."
}

$safeRoot = Join-Path $env:LOCALAPPDATA ("Temp\btc_laptop_agents_local_check\{0}" -f $RunId)
if (-not (Test-Path $safeRoot)) {
  New-Item -ItemType Directory -Force -Path $safeRoot | Out-Null
}

$buildTracker = Join-Path $safeRoot "pip-build-tracker"
if (-not (Test-Path $buildTracker)) {
  New-Item -ItemType Directory -Force -Path $buildTracker | Out-Null
}

# Best-effort: ensure current user has full control on temp tree.
try {
  icacls $safeRoot /grant "$($env:USERNAME):(OI)(CI)F" /T /C 2>$null | Out-Null
} catch {
  # ignore ACL adjustment failures
}

$env:TMP = $safeRoot
$env:TEMP = $safeRoot
$env:TMPDIR = $safeRoot
$env:PIP_CACHE_DIR = $safeRoot
$env:PIP_BUILD_TRACKER = $buildTracker

Write-Host ("Safe temp root: {0}" -f $safeRoot)
Write-Host ("TMP/TEMP/TMPDIR set to: {0}" -f $safeRoot)
Write-Host ("PIP_CACHE_DIR set to: {0}" -f $safeRoot)
Write-Host ("PIP_BUILD_TRACKER set to: {0}" -f $buildTracker)
