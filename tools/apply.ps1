param([switch]$NoTests)

$payload = Get-Clipboard
if (-not $payload -or $payload.Trim().Length -lt 10) {
  Write-Error "Clipboard is empty (or too short). Copy the payload I sent first, then run: .\tools\apply.ps1"
  exit 2
}

if ($NoTests) {
  $payload | python .\tools\safe_apply.py --stdin --no-tests
} else {
  $payload | python .\tools\safe_apply.py --stdin
}
