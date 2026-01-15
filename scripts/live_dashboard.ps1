# live_dashboard.ps1 - Start the Flask Live Dashboard
$Port = 5001
$env:DASHBOARD_PORT = $Port

Write-Host "Starting Live Trading Dashboard..." -ForegroundColor Cyan
Write-Host "URL: http://localhost:$Port" -ForegroundColor Green

# Start the Flask app in the background
Start-Process python -ArgumentList "src/laptop_agents/dashboard/app.py" -NoNewWindow

# Wait a moment
Start-Sleep -Seconds 2

# Open browser
Start-Process "http://localhost:$Port"
