param(
  [Parameter(Position=0)][string]$cmd="help"
)

if ($cmd -eq "install") {
  python -m pip install -e .
  exit 0
}

if ($cmd -eq "test") {
  pytest -q
  exit 0
}

if ($cmd -eq "demo") {
  python -m laptop_agents.cli run-mock --steps 250
  python -m laptop_agents.cli journal-tail --n 12
  exit 0
}

if ($cmd -eq "live") {
  python -m pip install httpx
  python -m laptop_agents.cli run-live-history --limit 500
  exit 0
}

Write-Host "Usage:"
Write-Host "  .\tools\dev.ps1 install"
Write-Host "  .\tools\dev.ps1 test"
Write-Host "  .\tools\dev.ps1 demo"
Write-Host "  .\tools\dev.ps1 live"
