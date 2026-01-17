# Run the BTC Laptop Agents Diagnostic Harness
# This script runs the full test suite and formats the output for AI feedback.

$ScriptPath = Join-Path $PSScriptRoot "scripts\test_everything.py"

if (Test-Path $ScriptPath) {
    # We use -u to force unbuffered output so you see it in real-time
    python -u $ScriptPath
} else {
    Write-Error "Could not find diagnostic script at $ScriptPath"
    exit 1
}
