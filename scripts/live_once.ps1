<#
Live Paper Trading Once Script
Runs the live paper trading mode once.
#>

# Resolve repo root from script location
$scriptDir = $PSScriptRoot
$repoRoot = Join-Path -Path $scriptDir -ChildPath ".."

# Use .venv Python if available
$pythonPath = Join-Path -Path $repoRoot -ChildPath ".venv\Scripts\python.exe"
if (-not (Test-Path -Path $pythonPath)) {
    $pythonPath = "python.exe"
}

# Default arguments
$symbol = "BTCUSDT"
$interval = "1m"
$limit = 500
$feesBps = 2
$slipBps = 0.5
$riskPct = 1.0
$stopBps = 30.0
$tpR = 1.5
$maxLeverage = 1.0
$intrabarMode = "conservative"

# Parse command line arguments
for ($i = 0; $i -lt $args.Length; $i++) {
    if ($args[$i] -eq "--symbol") {
        $symbol = $args[$i + 1]
        $i++
    } elseif ($args[$i] -eq "--interval") {
        $interval = $args[$i + 1]
        $i++
    } elseif ($args[$i] -eq "--limit") {
        $limit = $args[$i + 1]
        $i++
    } elseif ($args[$i] -eq "--fees-bps") {
        $feesBps = $args[$i + 1]
        $i++
    } elseif ($args[$i] -eq "--slip-bps") {
        $slipBps = $args[$i + 1]
        $i++
    } elseif ($args[$i] -eq "--risk-pct") {
        $riskPct = $args[$i + 1]
        $i++
    } elseif ($args[$i] -eq "--stop-bps") {
        $stopBps = $args[$i + 1]
        $i++
    } elseif ($args[$i] -eq "--tp-r") {
        $tpR = $args[$i + 1]
        $i++
    } elseif ($args[$i] -eq "--max-leverage") {
        $maxLeverage = $args[$i + 1]
        $i++
    } elseif ($args[$i] -eq "--intrabar-mode") {
        $intrabarMode = $args[$i + 1]
        $i++
    }
}

# Run live once
& $pythonPath -m laptop_agents.run --mode live --source bitunix --symbol $symbol --interval $interval --limit $limit --fees-bps $feesBps --slip-bps $slipBps --risk-pct $riskPct --stop-bps $stopBps --tp-r $tpR --max-leverage $maxLeverage --intrabar-mode $intrabarMode