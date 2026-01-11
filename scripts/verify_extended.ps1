# verify_extended.ps1 - Run 1000-candle stability test
Write-Host "Running Extended Mock Test (1000 candles)..."
python -m src.laptop_agents.run --mode orchestrated --source mock --limit 1000 --risk-pct 1.0
if ($LASTEXITCODE -ne 0) {
    Write-Error "Extended test failed with exit code $LASTEXITCODE"
    exit 1
}
# Verify artifacts exist
if (!(Test-Path "runs/latest/trades.csv")) {
    Write-Error "trades.csv not found!"
    exit 1
}
if (!(Test-Path "runs/latest/events.jsonl")) {
    Write-Error "events.jsonl not found!"
    exit 1
}
Write-Host "Extended test PASSED!"
