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

$env:TMP = $safeRoot
$env:TEMP = $safeRoot
$env:TMPDIR = $safeRoot
$env:PIP_CACHE_DIR = $safeRoot

Write-Host ("Safe temp root: {0}" -f $safeRoot)
Write-Host ("TMP/TEMP/TMPDIR set to: {0}" -f $safeRoot)
Write-Host ("PIP_CACHE_DIR set to: {0}" -f $safeRoot)
