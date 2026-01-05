param([int]$Poll = 60, [int]$RunMinutes = 60, [int]$Limit = 90)
$repo = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $repo

# Ensure required directories exist
New-Item -ItemType Directory -Force (Join-Path $repo "logs"), (Join-Path $repo "data") | Out-Null

# Ensure logs/events.jsonl exists
$eventsLog = Join-Path $repo "logs\events.jsonl"
if (!(Test-Path $eventsLog)) {
    New-Item -ItemType File -Path $eventsLog -Force | Out-Null
}

$pidFile = Join-Path $repo "data\live_paper.pid"
$outLog  = Join-Path $repo "logs\live_paper.out.txt"
$errLog  = Join-Path $repo "logs\live_paper.err.txt"
$control = Join-Path $repo "data\control.json"

if (!(Test-Path $control)) { '{ "paused": false, "extend_by_sec": 0 }' | Set-Content -Encoding UTF8 $control }

# Set environment variables
$env:LAPTOP_AGENTS_LOG_JSONL = (Resolve-Path $eventsLog).Path
$env:RUN_ID = "run-" + (Get-Date -Format "yyyyMMdd-HHmmss")

$runSeconds = 0
if ($RunMinutes -gt 0) { $runSeconds = $RunMinutes * 60 }

# Use .venv python directly (no activation)
$pythonExe = Join-Path $repo ".venv\Scripts\python.exe"
if (!(Test-Path $pythonExe)) {
    Write-Host "Error: .venv not found. Please run: python -m venv .venv"
    exit 1
}

$args = @(
  "scripts\live_paper_loop.py",
  "--symbol","BTCUSDT",
  "--interval","5m",
  "--limit","$Limit",
  "--journal","data\paper_journal.jsonl",
  "--state","data\paper_state.json",
  "--control","data\control.json",
  "--poll","$Poll",
  "--run-seconds","$runSeconds"
)

# Check if already running (idempotent)
function GetLivePaperProcess {
    # Check pidfile first
    if (Test-Path $pidFile) {
        try {
            $pidContent = Get-Content $pidFile -ErrorAction SilentlyContinue
            if ($pidContent -match '\d+') {
                $process = Get-Process -Id $pidContent -ErrorAction SilentlyContinue
                if ($process -ne $null) {
                    return $process
                }
            }
        } catch {}
    }
    
    # Scan for running processes
    $pythonProcesses = Get-Process -Name python,pythonw -ErrorAction SilentlyContinue
    foreach ($proc in $pythonProcesses) {
        try {
            $cmd = ($proc | Get-WmiObject Win32_Process).CommandLine
            if ($cmd -like "*live_paper_loop.py*" -or $cmd -like "*live_paper_loop*") {
                return $proc
            }
        } catch {}
    }
    return $null
}

$existing = GetLivePaperProcess
if ($existing -ne $null) {
    Write-Host "Live paper already running (PID $($existing.Id))"
    exit 0
}

$p = Start-Process -FilePath $pythonExe -ArgumentList $args -WorkingDirectory $repo `
  -PassThru -NoNewWindow -RedirectStandardOutput $outLog -RedirectStandardError $errLog

Set-Content -Path $pidFile -Value ($p.Id.ToString()) -Encoding ASCII
Start-Sleep -Seconds 2

# Verify it stayed alive; if not, print log tails immediately
try { Get-Process -Id $p.Id -ErrorAction Stop | Out-Null; $alive=$true } catch { $alive=$false }

if (-not $alive) {
  Write-Host "Live paper EXITED immediately. Showing log tails:"
  Write-Host "---- out ----"
  Get-Content $outLog -Tail 120 -ErrorAction SilentlyContinue
  Write-Host "---- err ----"
  Get-Content $errLog -Tail 120 -ErrorAction SilentlyContinue
  exit 1
}

Write-Host "Live paper running (PID $($p.Id))"
Write-Host "RUN_ID: $env:RUN_ID"
Write-Host "Events log: $eventsLog"
Write-Host "Runtime limit: $RunMinutes minutes (0=forever) | Poll=$Poll | Limit=$Limit"
Write-Host "Logs: $outLog / $errLog"
