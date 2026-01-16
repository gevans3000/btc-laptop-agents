Param(
    [string]$Profile = "default",
    [string]$Symbol = "BTCUSDT",
    [string]$Interval = "1m",
    [switch]$Bitunix = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Get repository root
$repoRoot = $PSScriptRoot
while (-not (Test-Path -Path (Join-Path $repoRoot "pyproject.toml"))) {
    $repoRoot = Split-Path $repoRoot -Parent
    if ($repoRoot -eq $null) {
        throw "Cannot find repository root (pyproject.toml)"
    }
}

# Ensure paper directory exists
$paperDir = Join-Path -Path $repoRoot -ChildPath "paper"
if (-not (Test-Path $paperDir)) {
    New-Item -ItemType Directory -Path $paperDir -Force | Out-Null
}

# Check if already running
$pidFile = Join-Path -Path $paperDir -ChildPath "mvp.pid"
if (Test-Path $pidFile) {
    $livePid = (Get-Content $pidFile | Out-String).Trim()
    if ($livePid -match '^\d+$') {
        $process = Get-Process -Id $livePid -ErrorAction SilentlyContinue
        if ($process -ne $null) {
            Write-Host "Live process is already running (PID $livePid)" -ForegroundColor Yellow
            Write-Host "Use .\scripts\mvp_stop_live.ps1 to stop it first"
            exit 1
        }
        else {
            # Stale PID file, remove it
            Remove-Item $pidFile -Force
        }
    }
}

# Start live process in background
$logFile = Join-Path -Path $paperDir -ChildPath "live.out.txt"
$errFile = Join-Path -Path $paperDir -ChildPath "live.err.txt"

$source = "mock"
if ($Bitunix) { $source = "bitunix" }

$commandArgs = "--mode live --source $source --symbol $Symbol --interval $Interval --strategy $Profile"
$pythonPath = "'$PSScriptRoot\..\.venv\Scripts\python.exe'"
 
Write-Host "Starting live paper trading..."
Write-Host "Profile: $Profile"
Write-Host "Symbol:  $Symbol"
Write-Host "Source:  $source"
Write-Host "Logs:    $logFile"
 
# Start process and capture PID
$process = Start-Process -FilePath "powershell" -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-Command", "& $pythonPath -m src.laptop_agents.run $commandArgs" -RedirectStandardOutput $logFile -RedirectStandardError $errFile -PassThru -NoNewWindow

# Write PID to file
$process.Id | Out-File $pidFile -Force

Write-Host "Live paper trading started with PID $($process.Id)" -ForegroundColor Green
Write-Host "Use .\scripts\mvp_status.ps1 to check status"
Write-Host "Use .\scripts\mvp_stop_live.ps1 to stop"

# Give it a moment to start
Start-Sleep -Seconds 2

# Verify it's still running
$verifyProcess = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
if ($verifyProcess -eq $null) {
    Write-Host "Error: Process $($process.Id) failed to start. Check $errFile" -ForegroundColor Red
    Remove-Item $pidFile -Force
    exit 1
}

exit 0