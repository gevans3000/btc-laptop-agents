param()
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $repo
Set-Location $repo
powershell -ExecutionPolicy Bypass -File .\scripts\stop_live_paper.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\stop_dashboard.ps1
Write-Host "Stop All complete."
