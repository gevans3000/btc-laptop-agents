# dashboard_up.ps1 - Serve the latest run dashboard
# Usage: .\scripts\dashboard_up.ps1

$LatestDir = "runs/latest"
if (!(Test-Path $LatestDir)) {
    Write-Error "No latest run found in $LatestDir"
    exit 1
}

$Port = 8000
Write-Host "Starting Dashboard Server on http://localhost:$Port"
Write-Host "Serving from: $(Get-Item $LatestDir | Select-Object -ExpandProperty FullName)"
Write-Host "Press Ctrl+C to stop."

# Open browser
Start-Process "http://localhost:$Port/summary.html"

# Serve using Python's built-in http server
python -m http.server $Port --directory $LatestDir
