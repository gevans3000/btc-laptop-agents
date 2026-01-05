param()
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $repo
$pidFile = Join-Path $repo "data\dashboard.pid"
function GetPid($p){ if(!(Test-Path $p)){return $null}; $t=Get-Content $p -Raw -ErrorAction SilentlyContinue; if($null -eq $t){return $null}; $m=[regex]::Match($t,"\d+"); if($m.Success){return [int]$m.Value}; return $null }
$procId = GetPid $pidFile
if ($procId) { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue | Out-Null; try { & taskkill /PID $procId /T /F | Out-Null } catch {} }
if (Test-Path $pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue | Out-Null }
Write-Host "Dashboard stopped."
