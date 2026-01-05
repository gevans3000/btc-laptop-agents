param([int]$Port = 8000)
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $repo
New-Item -ItemType Directory -Force (Join-Path $repo "logs"), (Join-Path $repo "data") | Out-Null
$pidFile = Join-Path $repo "data\dashboard.pid"
$outLog  = Join-Path $repo "logs\dashboard.out.txt"
$errLog  = Join-Path $repo "logs\dashboard.err.txt"
function GetPid($p){ if(!(Test-Path $p)){return $null}; $t=Get-Content $p -Raw -ErrorAction SilentlyContinue; if($null -eq $t){return $null}; $m=[regex]::Match($t,"\d+"); if($m.Success){return [int]$m.Value}; return $null }
$old = GetPid $pidFile
if ($old) { Stop-Process -Id $old -Force -ErrorAction SilentlyContinue | Out-Null; try { & taskkill /PID $old /T /F | Out-Null } catch {} }
if (Test-Path $pidFile) { Remove-Item $pidFile -Force -ErrorAction SilentlyContinue | Out-Null }
$p = Start-Process -FilePath "python" -ArgumentList @("scripts\dashboard_server.py","--port","$Port","--bind","127.0.0.1") `
  -WorkingDirectory $repo -PassThru -NoNewWindow -RedirectStandardOutput $outLog -RedirectStandardError $errLog
Set-Content -Path $pidFile -Value ($p.Id.ToString()) -Encoding ASCII
Write-Host "Dashboard running on http://127.0.0.1:$Port/ (PID $($p.Id))"
