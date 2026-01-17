# Run the BTC Laptop Agents Diagnostic Harness
# This script runs the full test suite and formats the output for AI feedback.

$ErrorActionPreference = "Continue" # Check all, don't stop on first error
# Fix for Unicode characters in Python output and PowerShell console on Windows
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ScriptPath = Join-Path $PSScriptRoot "scripts\test_everything.py"
$LogFile = "test_out.txt"

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

# Wrap execution to capture all output to file
& {
    Write-Section "System & Environment Prerequisites"

    # 1. Python Version
    Run-Check "Python Version (>= 3.10)" {
        $ver = python --version 2>&1
        if ($ver -match "Python 3\.(1[0-9]|[2-9][0-9])") { return $true }
        throw "Version mismatch: $ver (Must be >= 3.10)"
    }

    # 2. Virtual Environment
    Run-Check "Virtual Environment" {
        if (-not $env:VIRTUAL_ENV) {
            # Secondary check: verify we can import project dependencies
            python -c "import httpx; import pandas" 2>$null
            if ($LASTEXITCODE -ne 0) { throw "No VIRTUAL_ENV set and dependencies missing." }
        }
    }

    # 3. Dependency Integrity
    Run-Check "Dependency Integrity (pip check)" {
        $out = pip check 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            Write-Host "`n$($out.Trim())" -ForegroundColor DarkGray
            throw "pip check detected broken dependencies."
        }
    }

    # 4. .env File
    Run-Check ".env Configuration" {
        if (-not (Test-Path ".env")) { throw ".env file is missing." }
        $content = Get-Content ".env" -Raw
        if ($content -notmatch "BITUNIX_API_KEY") { throw "BITUNIX_API_KEY seems missing in .env" }
    }

    # 5. Disk Space
    Run-Check "Disk Space" {
        $drive = Get-Volume -DriveLetter "C"
        if ($drive.SizeRemaining -lt 1GB) { throw "Less than 1GB disk space remaining on C: drive." }
    }

    # 6. Resource Usage
    Run-Check "System Resources" {
        $mem = Get-CimInstance Win32_OperatingSystem
        $totalGB = [math]::Round($mem.TotalVisibleMemorySize / 1MB, 2)
        $freeGB = [math]::Round($mem.FreePhysicalMemory / 1MB, 2)
        $cpu = Get-CimInstance Win32_Processor | Select-Object -ExpandProperty LoadPercentage
        Write-Host "`n   RAM: $freeGB GB Free / $totalGB GB Total" -ForegroundColor DarkGray
        Write-Host "   CPU Load: $cpu%" -ForegroundColor DarkGray
    }

    Write-Section "Exchange Connectivity Probes"

    # We construct a temporary python script to test connectivity by importing providers
    $PyProbeScript = @"
import sys
import os
import importlib
import warnings
import traceback

# Suppress some noisy warnings for cleaner output
warnings.filterwarnings("ignore")

# Ensure src is in path
sys.path.append(os.path.join(os.getcwd(), 'src'))

def probe(name, module, class_name, symbol, method):
    try:
        mod = importlib.import_module(module)
        cls = getattr(mod, class_name)
        # Instantiate (some providers need symbol in init)
        try:
            p = cls(symbol=symbol)
        except:
            p = cls()

        # Call the probe method
        if hasattr(p, method):
            fn = getattr(p, method)
            try:
                res = fn()
                # Simple check: if it returns successfully, we consider it connected
                print(f"   [PASS] {name}: Reachable")
            except Exception as e:
                err_str = str(e)
                # Print repr for more detail if str is short/confusing (like '0')
                if len(err_str) < 5:
                    err_str = repr(e)

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

# Map: Name -> (Module, Class, Symbol, MethodToCheck)
probe_map = [
    ('Bitunix', 'laptop_agents.data.providers.bitunix_futures', 'BitunixFuturesProvider', 'BTCUSDT', 'funding_rate'),
    ('Binance', 'laptop_agents.data.providers.binance_futures', 'BinanceFuturesProvider', 'BTCUSDT', 'funding_8h'),
    ('Bybit',   'laptop_agents.data.providers.bybit_derivatives', 'BybitDerivativesProvider', 'BTCUSDT', 'snapshot_derivatives'),
    ('Kraken',  'laptop_agents.data.providers.kraken_spot', 'KrakenSpotProvider', 'XBTUSDT', 'klines'),
    ('OKX',     'laptop_agents.data.providers.okx_swap', 'OkxSwapProvider', 'BTC-USDT-SWAP', 'snapshot_derivatives'),
]

for p in probe_map:
    probe(*p)
"@
    $ProbeFile = "temp_probe.py"
    $PyProbeScript | Out-File $ProbeFile -Encoding utf8
    python $ProbeFile
    Remove-Item $ProbeFile -ErrorAction SilentlyContinue

    Write-Section "Running Main Diagnostic Harness"
    if (Test-Path $ScriptPath) {
        python -u $ScriptPath

        if ($LASTEXITCODE -eq 0) {
            Write-Host "`n[SUCCESS] Main harness passed." -ForegroundColor Green
        } else {
            Write-Host "`n[WARNING] Main harness reported failures." -ForegroundColor Yellow
        }
    } else {
        Write-Error "script/test_everything.py not found at $ScriptPath"
    }

    Write-Section "System Info Snapshot"
    try {
        python -c "import platform; print(f'OS: {platform.system()} {platform.release()}'); print(f'Python: {platform.python_version()}');"
    } catch {}

    try {
        git status -s 2>$null
    } catch {}

} *>&1 | Tee-Object -FilePath $LogFile

Write-Host "`n[Full Diagnostic Complete]" -ForegroundColor Cyan
Write-Host "Output captured in: $LogFile" -ForegroundColor Cyan
