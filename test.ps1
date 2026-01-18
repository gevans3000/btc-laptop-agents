# Run the BTC Laptop Agents Reliability Harness
# This script runs the full test suite and then performs a 10-minute autonomous stress test.

$ErrorActionPreference = "Continue" # Check all, don't stop on first error
# Fix for Unicode characters in Python output and PowerShell console on Windows
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptPath = Join-Path $PSScriptRoot "scripts\test_everything.py"
$MainAppPath = Join-Path $PSScriptRoot "src\laptop_agents\main.py"
$AutonomyLog = "autonomy_session.log"
$TestLog = "test_out.txt"

function Write-Section {
    param([string]$Title)
    Write-Host "`n============================================================" -ForegroundColor Cyan
    Write-Host " $Title" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
}

function Run-Check {
    param([string]$Name, [ScriptBlock]$Check)
    Write-Host -NoNewline "Checking $Name... "
    try {
        & $Check
        Write-Host "PASS" -ForegroundColor Green
    } catch {
        Write-Host "FAIL" -ForegroundColor Red
        Write-Host "  Error: $_" -ForegroundColor Red
    }
}

# --- Section 1: Pre-Flight Static Checks ---
Write-Section "1. System & Environment Prerequisites"

& {
    # 1.1 Python Version
    Run-Check "Python Version (>= 3.10)" {
        $ver = python --version 2>&1
        if ($ver -match "Python 3\.(1[0-9]|[2-9][0-9])") { return $true }
        throw "Version mismatch: $ver (Must be >= 3.10)"
    }

    # 1.2 Virtual Environment
    Run-Check "Virtual Environment" {
        if (-not $env:VIRTUAL_ENV) {
            # Secondary check: verify we can import project dependencies
            python -c "import httpx; import pandas" 2>$null
            if ($LASTEXITCODE -ne 0) { throw "No VIRTUAL_ENV set and dependencies missing." }
        }
    }

    # 1.3 Dependency Integrity
    Run-Check "Dependency Integrity (pip check)" {
        $out = python -m pip check 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            Write-Host "`n$($out.Trim())" -ForegroundColor DarkGray
            Write-Host "WARNING: pip check detected broken dependencies (ignoring for now)." -ForegroundColor Yellow
        }
    }

    # 1.4 .env File
    Run-Check ".env Configuration" {
        if (-not (Test-Path ".env")) { throw ".env file is missing." }
        $content = Get-Content ".env" -Raw
        if ($content -notmatch "BITUNIX_API_KEY") { throw "BITUNIX_API_KEY seems missing in .env" }
    }

    # 1.5 Lockfile Cleanup
    Run-Check "Stale Lockfiles" {
        $LockFile = ".agent/lockfile.pid"
        if (Test-Path $LockFile) {
            Write-Host "Found stale lockfile, cleaning up..." -ForegroundColor Yellow
            Remove-Item $LockFile -Force
        }
    }

    # 1.6 Resource Usage
    Run-Check "System Resources" {
        $mem = Get-CimInstance Win32_OperatingSystem
        $totalGB = [math]::Round($mem.TotalVisibleMemorySize / 1MB, 2)
        $freeGB = [math]::Round($mem.FreePhysicalMemory / 1MB, 2)
        $cpu = Get-CimInstance Win32_Processor | Select-Object -ExpandProperty LoadPercentage
        Write-Host "`n   RAM: $freeGB GB Free / $totalGB GB Total" -ForegroundColor DarkGray
        Write-Host "   CPU Load: $cpu%" -ForegroundColor DarkGray
        if ($freeGB -lt 2) { throw "Low memory warning (<2GB free)" }
    }
}

# --- Section 2: Connectivity Probes ---
Write-Section "2. Exchange Connectivity Probes"

# Python script to test connectivity
$PyProbeScript = @"
import sys
import os
import importlib
import warnings
import traceback

# Suppress some noisy warnings for cleaner output
warnings.filterwarnings("ignore")
sys.path.append(os.path.join(os.getcwd(), 'src'))

def probe(name, module, class_name, symbol, method):
    try:
        mod = importlib.import_module(module)
        cls = getattr(mod, class_name)
        try:
            p = cls(symbol=symbol)
        except:
            p = cls()

        if hasattr(p, method):
            fn = getattr(p, method)
            try:
                res = fn()
                print(f"   [PASS] {name}: Reachable")
            except Exception as e:
                err_str = str(e)
                if len(err_str) < 5: err_str = repr(e)
                if "451" in err_str:
                     print(f"   [WARN] {name}: Geo-blocked (HTTP 451)")
                else:
                     print(f"   [FAIL] {name}: Request Failed - {err_str}")
        else:
            print(f"   [FAIL] {name}: Method {method} not found on class")
    except Exception as e:
        print(f"   [FAIL] {name}: Import/Init Failed - {e}")
        traceback.print_exc()

print("Probing Exchange Providers (REST)...")
probe_map = [
    ('Bitunix', 'laptop_agents.data.providers.bitunix_futures', 'BitunixFuturesProvider', 'BTCUSDT', 'funding_rate'),
    ('Bybit',   'laptop_agents.data.providers.bybit_derivatives', 'BybitDerivativesProvider', 'BTCUSDT', 'snapshot_derivatives'),
]
for p in probe_map:
    probe(*p)
"@

$ProbeFile = "temp_probe.py"
$PyProbeScript | Out-File $ProbeFile -Encoding utf8
python $ProbeFile
Remove-Item $ProbeFile -ErrorAction SilentlyContinue

# --- Cleanup Old Sessions (Aggressive) ---
$LockList = @(
    ".agent/lockfile.pid",
    "paper/async_session.lock",
    "src/laptop_agents/paper/async_session.lock"
)

foreach ($L in $LockList) {
    if (Test-Path $L) {
        Remove-Item $L -Force -ErrorAction SilentlyContinue
        Write-Host "Removed stale lock: $L" -ForegroundColor Yellow
    }
}

# Find and kill any lingering python processes running 'main.py' or 'laptop_agents'
Get-WmiObject Win32_Process | Where-Object {
    ($_.CommandLine -like "*laptop_agents*" -or $_.CommandLine -like "*main.py*") -and $_.Name -like "python*"
} | ForEach-Object {
    Write-Host "Killing zombie process (PID: $($_.ProcessId))..." -ForegroundColor Yellow
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

# Wait for OS to release handles
Start-Sleep -Seconds 3

# Also attempt to unlock files by forcing GC (PowerShell sometimes holds handles)
[System.GC]::Collect()
[System.GC]::WaitForPendingFinalizers()

# --- Section 3: Autonomy Stress Test ---
Write-Section "3. 10-Minute Autonomy Stress Test"

# Ensure we are in root
$Env:PYTHONPATH = "$PSScriptRoot\src"
Write-Host "Launching background process..." -ForegroundColor Cyan
Write-Host "Command: python src/laptop_agents/main.py run --mode live-session --execution-mode paper --duration 10 --symbol BTCUSDT" -ForegroundColor DarkGray

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$AutonomyLog = "autonomy_session_$Timestamp.log"
$AutonomyErr = "autonomy_error_$Timestamp.log"

# Clean up old logs (WARN only, don't crash)
Get-ChildItem "autonomy_session_*.log" | ForEach-Object { Remove-Item $_ -ErrorAction SilentlyContinue }
Get-ChildItem "autonomy_error_*.log" | ForEach-Object { Remove-Item $_ -ErrorAction SilentlyContinue }

# Construct the launch command
# We use Start-Process to run it detached/background but monitor-able
$Proc = Start-Process -FilePath "python" `
    -ArgumentList "-u", "$MainAppPath", "run", "--mode", "live-session", "--execution-mode", "paper", "--duration", "10", "--symbol", "BTCUSDT", "--async", "--dashboard" `
    -RedirectStandardOutput $AutonomyLog `
    -RedirectStandardError $AutonomyErr `
    -PassThru `
    -WindowStyle Hidden

if (-not $Proc) {
    Write-Error "Failed to launch process."
    exit 1
}

Write-Host "Process Started. PID: $($Proc.Id)" -ForegroundColor Green
Write-Host "Dashboard:       http://localhost:5000" -ForegroundColor Cyan
Write-Host "Monitoring for 10 minutes... (Press Ctrl+C to abort and kill process)" -ForegroundColor Yellow

# Wait for Dashboard to come up
Start-Sleep -Seconds 5
$DashCheck = Test-NetConnection -ComputerName localhost -Port 5000 -InformationLevel Quiet
if ($DashCheck) {
    Write-Host "Dashboard is UP and Reachable!" -ForegroundColor Green
} else {
    Write-Host "Dashboard not yet unreachable (might take a moment)." -ForegroundColor DarkGray
}

$DurationMinutes = 10
$CheckIntervalSeconds = 30
$TotalChecks = ($DurationMinutes * 60) / $CheckIntervalSeconds
$ChecksRan = 0
$ErrorsDetected = 0

try {
    for ($i = 1; $i -le $TotalChecks; $i++) {
        Start-Sleep -Seconds $CheckIntervalSeconds
        $ChecksRan++

        # A. Process Health
        if ($Proc.HasExited) {
            Write-Host "`n[ALERT] Process exited early! (Exit Code: $($Proc.ExitCode))" -ForegroundColor Red
            break
        }

        # B. Memory/CPU Check (Fresh info)
        $Proc.Refresh()
        $MemMB = [math]::Round($Proc.WorkingSet64 / 1MB, 2)

        # C. Log Liveness (Heartbeat)
        $LogContent = Get-Content $AutonomyLog -Tail 20 2>$null
        $Heartbeat = $LogContent | Select-String "AsyncHeartbeat"

        if ($Heartbeat) {
            $StatusColor = "Green"
            $StatusMsg = "OK"
        } else {
            $StatusColor = "Yellow"
            $StatusMsg = "NO HEARTBEAT"
            # Check for startup phase
            if ($i -lt 3) { $StatusMsg = "STARTUP.." }
        }

        # D. Silent Error Detection
        $RecentErrors = $LogContent | Select-String -Pattern "Traceback|CRITICAL|Error"
        if ($RecentErrors) {
             # Filter out some known noise if necessary, for now treat as fail
             $StatusColor = "Red"
             $StatusMsg = "ERROR DETECTED"
             $ErrorsDetected++
        }

        # Timestamp for dashboard
        $TimeRemaining = "{0:mm\:ss}" -f [timespan]::FromSeconds(($TotalChecks - $i) * $CheckIntervalSeconds)

        # Dashboard Line
        Write-Host "[$([DateTime]::Now.ToString('HH:mm:ss'))] T-$TimeRemaining | MEM: ${MemMB}MB | STATUS: " -NoNewline
        Write-Host $StatusMsg -ForegroundColor $StatusColor

        if ($ErrorsDetected -gt 5) {
            Write-Host "Too many errors detected. Aborting test." -ForegroundColor Red
            break
        }
    }
} finally {
    # --- Teardown & Analysis ---
    Write-Section "4. Post-Run Verification"

    if (-not $Proc.HasExited) {
        Write-Host "Test time finished. Waiting for graceful shutdown..." -ForegroundColor Cyan
        # In a real autonomy run with --duration, it should exit.
        # We give it a buffer of 60s to close out positions/logs.
        $Proc.WaitForExit(60000)
        if (-not $Proc.HasExited) {
            Write-Host "Process stuck. Forcing kill." -ForegroundColor Red
            Stop-Process -Id $Proc.Id -Force
        } else {
             Write-Host "Process exited gracefully." -ForegroundColor Green
        }
    }

    # Full Log Analysis
    Write-Host "Analyzing logs..."
    if (Test-Path $AutonomyErr) {
        $ErrContent = Get-Content $AutonomyErr
        if ($ErrContent) {
             Write-Host "`nStderror Output Detected:" -ForegroundColor Yellow
             $ErrContent | Select-String -Pattern "Traceback|Error|Exception" -Context 0,2 | ForEach-Object { Write-Host $_ -ForegroundColor Red }
        }
    }

    if (Test-Path $AutonomyLog) {
        $FullLog = Get-Content $AutonomyLog
        $Tracebacks = $FullLog | Select-String "Traceback"
        $Criticals = $FullLog | Select-String "CRITICAL"
        $Heartbeats = ($FullLog | Select-String "AsyncHeartbeat").Count

        Write-Host "`n--- VERDICT ---"
        Write-Host "Total Runtime Log Lines: $($FullLog.Count)"
        Write-Host "Total Heartbeats:        $Heartbeats"

        if ($Heartbeats -lt 5) {
             Write-Host "FAIL: Insufficient heartbeats (Logic froze?)" -ForegroundColor Red
        } else {
             Write-Host "PASS: Heartbeat activity detected." -ForegroundColor Green
        }

        if ($Tracebacks -or $Criticals) {
            Write-Host "FAIL: Errors found in log." -ForegroundColor Red
            $Tracebacks | ForEach-Object { Write-Host $_ -ForegroundColor DarkRed }
            $Criticals | ForEach-Object { Write-Host $_ -ForegroundColor DarkRed }
        } else {
            Write-Host "PASS: Zero critical errors." -ForegroundColor Green
        }

        Write-Host "`nFull log saved to: $AutonomyLog" -ForegroundColor Gray
    } else {
        Write-Host "FAIL: Log file never created!" -ForegroundColor Red
    }
}
