param(
  [ValidateSet("quick","full")]
  [string]$Mode = "quick"
)

$ErrorActionPreference = "Stop"

function Run-Step {
  param([string]$Name, [scriptblock]$Cmd)
  Write-Host ""
  Write-Host ("=== {0} ===" -f $Name) -ForegroundColor Cyan
  & $Cmd
  if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit=$LASTEXITCODE)" }
}

try {
  $py = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
  if (!(Test-Path $py)) { throw "Missing venv python: $py  (create it: python -m venv .venv)" }

  Run-Step "COMPILATION" { & $py -m compileall .\src }

  Run-Step "SELFTEST (conservative)" { & $py -m src.laptop_agents.run --mode selftest --intrabar-mode conservative }
  Run-Step "SELFTEST (optimistic)"   { & $py -m src.laptop_agents.run --mode selftest --intrabar-mode optimistic }

  if ($Mode -eq "full") {
    Run-Step "MOCK BACKTEST (sanity)" { & $py -m src.laptop_agents.run --mode backtest --source mock --limit 500 --backtest 500 --intrabar-mode conservative }
    Run-Step "MOCK VALIDATE (sanity)" { & $py -m src.laptop_agents.run --mode validate --source mock --limit 2000 --validate-splits 3 --validate-train 400 --validate-test 200 --grid "sma=10,30;12,36; stop=20,30; tp=1.0,1.5" --intrabar-mode conservative }
  }

  Write-Host ""
  Write-Host "VERIFY: PASS" -ForegroundColor Green
  exit 0
}
catch {
  Write-Host ""
  Write-Host "VERIFY: FAIL" -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Red
  exit 1
}
