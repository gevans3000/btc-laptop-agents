param(
  [ValidateSet("mock","bitunix")] [string]$source="mock",
  [string]$symbol="BTCUSDT",
  [string]$interval="1m",
  [int]$limit=200
)

$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $repo ".venv\Scripts\python.exe"
& $py -m laptop_agents.run --source $source --symbol $symbol --interval $interval --limit $limit
