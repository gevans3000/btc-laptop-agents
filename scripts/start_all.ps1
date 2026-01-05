param(
  [int]$Port = 8000,
  [int]$Poll = 30,
  [int]$RunMinutes = 60,
  [int]$Limit = 90
)

$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $repo
Set-Location $repo

function Get-SafePid($path) {
  if (!(Test-Path $path)) { return $null }
  $txt = Get-Content $path -Raw -ErrorAction SilentlyContinue
  if ($null -eq $txt) { return $null }
  $txt = $txt.Trim()
  if (!$txt) { return $null }
  $m = [regex]::Match($txt, "\d+")
  if ($m.Success) { return [int]$m.Value }
  return $null
}

powershell -ExecutionPolicy Bypass -File .\scripts\stop_dashboard.ps1 | Out-Null
powershell -ExecutionPolicy Bypass -File .\scripts\start_dashboard.ps1 -Port $Port

powershell -ExecutionPolicy Bypass -File .\scripts\stop_live_paper.ps1 | Out-Null
powershell -ExecutionPolicy Bypass -File .\scripts\start_live_paper.ps1 -Poll $Poll -RunMinutes $RunMinutes -Limit $Limit

Start-Sleep -Seconds 1
$lp = Get-SafePid ".\data\live_paper.pid"
if (!$lp) {
  Write-Host "ERROR: live paper did not create data\live_paper.pid"
  if (Test-Path .\logs\live_paper.err.txt) { Get-Content .\logs\live_paper.err.txt -Tail 120 }
  exit 1
}
if (!(Get-Process -Id $lp -ErrorAction SilentlyContinue)) {
  Write-Host "ERROR: live paper PID $lp is not running."
  if (Test-Path .\logs\live_paper.err.txt) { Get-Content .\logs\live_paper.err.txt -Tail 120 }
  exit 1
}

# open best page available
if (Test-Path ".\dashboard\monitor.html") {
  Start-Process "http://127.0.0.1:$Port/dashboard/monitor.html"
} else {
  Start-Process "http://127.0.0.1:$Port/dashboard/"
}

Write-Host "Start All complete. Dashboard + Live paper are running. Live PID=$lp"
