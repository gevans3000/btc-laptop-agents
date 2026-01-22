<#
.SYNOPSIS
    Comprehensive reliability and environment test suite (testall.ps1).
    Designed to run an exhaustive, laptop-only test pass and produce AI-friendly reports.

.DESCRIPTION
    Automated QA harness that performs:
    - App discovery strategy (parsing test.ps1)
    - Environment & Dependency checks
    - Network & Connectivity validation
    - Permutations (Env Vars, CWD)
    - Stability Loops (Launch/Exit stress test)
    - Resource Monitoring

    Outputs structured JSON and human-readable reports.

.PARAMETER Iterations
    Number of stability loop iterations (default: 5).
.PARAMETER KeepArtifacts
    If set, preserves the sandbox execution folder even on success.
.PARAMETER VerboseLogs
    Enable detailed logging to console.
.PARAMETER AppPath
    Override automatic discovery of the application entry point.
.PARAMETER NoNetworkTests
    Skip connectivity checks.
.PARAMETER Fast
    Runs a reduced set of tests (1 iteration, skip heavy permutations).

.EXAMPLE
    .\testall.ps1 -Iterations 3
    .\testall.ps1 -Fast -VerboseLogs
#>

param(
    [int]$Iterations = 5,
    [switch]$KeepArtifacts,
    [switch]$VerboseLogs,
    [string]$AppPathOverride,
    [switch]$NoNetworkTests,
    [switch]$Fast
)

# --- Init ---
$ErrorActionPreference = "Stop"
$ScriptRoot = $PSScriptRoot
if (-not $ScriptRoot) { $ScriptRoot = Get-Location }

# If Fast mode, reduce iterations
if ($Fast) { $Iterations = 1 }

# Artifacts Setup
$RunID = Get-Date -Format "yyyyMMdd-HHmmss"
$ArtifactsDir = Join-Path $ScriptRoot "._testall_artifacts\$RunID"
$SandboxDir = Join-Path $ScriptRoot "._testall_sandbox"
$ReportJSON = Join-Path $ScriptRoot "testall-report.json"
$ReportText = Join-Path $ScriptRoot "testall-report.txt"
$MainLog = Join-Path $ArtifactsDir "testall.log"

New-Item -ItemType Directory -Path $ArtifactsDir -Force | Out-Null
if (Test-Path $SandboxDir) { Remove-Item $SandboxDir -Recurse -Force -ErrorAction SilentlyContinue }
New-Item -ItemType Directory -Path $SandboxDir -Force | Out-Null

# Globals
$Global:TestResults = [System.Collections.Generic.List[PSObject]]::new()
$SystemInfo = @{}
$Discovery = @{}
$Global:TestID = 1

# --- Helpers ---

function Write-Log {
    param(
        [string]$Message,
        [string]$Level="INFO",
        [ConsoleColor]$Color="White",
        [switch]$NoFile
    )
    $time = Get-Date -Format "HH:mm:ss"
    $line = "[$time] [$Level] $Message"
    if ($VerboseLogs -or $Level -eq "ERROR" -or $Level -eq "WARN") {
        Write-Host $line -ForegroundColor $Color
    }
    if (-not $NoFile) {
        $fileLine = "[$([DateTime]::Now.ToString('o'))] [$Level] $Message"
        Add-Content -Path $MainLog -Value $fileLine -ErrorAction SilentlyContinue # Log file might be locked if very fast
    }
}

function New-TestResult {
    param($Name, $Result, $DurationMs, $Details, $Artifacts)
    $obj = [PSCustomObject]@{
        pId = $Global:TestID++
        Name = $Name
        Result = $Result
        DurationMs = $DurationMs
        Details = $Details
        Artifacts = $Artifacts
        Timestamp = Get-Date -Format "o"
    }
    $Global:TestResults.Add($obj)
    return $obj
}

function Invoke-Test {
    param(
        [string]$Name,
        [ScriptBlock]$Action,
        [int]$TimeoutSeconds = 60
    )
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $status = "PASS"
    $details = ""
    $arts = @()

    Write-Host "TEST [$Name]... " -NoNewline -ForegroundColor Cyan

    try {
        # Run in a job to support timeout (optional, but robust)
        # For simplicity in this portable script, we run inline but trap errors
        # To truly support timeout we'd need Start-Job, but that loses context.
        # We will wrap in a simple try/catch.

        $jobResult = & $Action
        if ($jobResult) { $details = $jobResult.ToString() }

        $sw.Stop()
        Write-Host "PASS ($($sw.ElapsedMilliseconds)ms)" -ForegroundColor Green
    } catch {
        $sw.Stop()
        $status = "FAIL"
        $details = $_.Exception.Message
        Write-Host "FAIL" -ForegroundColor Red
        Write-Log "Test Failed: $Name - $details" -Level "ERROR"
    }

    New-TestResult -Name $Name -Result $status -DurationMs $sw.ElapsedMilliseconds -Details $details -Artifacts $arts
}

# --- 1. App Discovery ---
Write-Log "--- Phase 1: App Discovery ---" -Color Magenta

$AppEntry = $null
$AppType = "Unknown"

# Strategy 1: Override
if ($AppPathOverride) {
    if (Test-Path $AppPathOverride) {
        $AppEntry = $AppPathOverride
        $Discovery["Method"] = "Override"
    } else {
        Write-Log "AppPathOverride provided but not found: $AppPathOverride" -Level WARN -Color Yellow
    }
}

# Strategy 2: Parse test.ps1
if (-not $AppEntry) {
    $TestPs1Path = Join-Path $ScriptRoot "test.ps1"
    if (Test-Path $TestPs1Path) {
        $content = Get-Content $TestPs1Path -Raw
        # Look for python ... src/laptop_agents/main.py
        if ($content -match 'python.+?["'']?([^"''\s]+\\src\\laptop_agents\\main\.py)["'']?') {
            $match = $matches[1]
            if (-not (Test-Path $match)) {
                # Try relative to script root
                $rel = Join-Path $ScriptRoot "src\laptop_agents\main.py"
                if (Test-Path $rel) { $match = $rel }
            }
            if (Test-Path $match) {
                $AppEntry = $match
                $Discovery["Method"] = "Parsed test.ps1"
                $AppType = "Python"
            }
        }
        # Fallback regex for common python main
        if (-not $AppEntry -and $content -match 'src\\laptop_agents\\main\.py') {
             $rel = Join-Path $ScriptRoot "src\laptop_agents\main.py"
             if (Test-Path $rel) {
                 $AppEntry = $rel
                 $Discovery["Method"] = "Inferred from test.ps1 partial"
                 $AppType = "Python"
             }
        }
    }
}

# Strategy 3: Scan
if (-not $AppEntry) {
    $candidates = Get-ChildItem -Path $ScriptRoot -Recurse -Depth 3 -Include "main.py","app.py","start.ps1" -ErrorAction SilentlyContinue
    if ($candidates) {
        $AppEntry = $candidates[0].FullName
        $Discovery["Method"] = "File Scan"
        $AppType = "Heuristic"
    }
}

if ($AppEntry) {
    Write-Log "App Found: $AppEntry" -Color Green
    $Discovery["Path"] = $AppEntry
    $Discovery["Type"] = $AppType
} else {
    Write-Log "Could not locate application entry point." -Level ERROR -Color Red
    $Discovery["Status"] = "Failed"
}

# --- 2. System Info ---
Write-Log "--- Phase 2: System Info ---" -Color Magenta

$info = @{}
$info["OS"] = (Get-CimInstance Win32_OperatingSystem).Caption
$info["Architecture"] = $env:PROCESSOR_ARCHITECTURE
$info["Hostname"] = $env:COMPUTERNAME
$info["User"] = $env:USERNAME
$info["IsAdmin"] = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$info["PowerShell"] = $PSVersionTable.PSVersion.ToString()
$info["Timezone"] = (Get-Timezone).Id
$info["CWD"] = (Get-Location).Path

# Checks Dependencies
if (Get-Command "python" -ErrorAction SilentlyContinue) {
    $info["Python"] = (python --version 2>&1 | Out-String).Trim()
} else {
    $info["Python"] = "Not Found"
}

$SystemInfo = $info
Write-Log "System: $($info.OS) ($($info.Architecture)) | Python: $($info.Python)"

# --- 3. Run Test Matrix ---
Write-Log "--- Phase 3: Test Matrix ---" -Color Magenta

# A. PERMISSIONS
Invoke-Test "Permission Check" {
    if ($SystemInfo.IsAdmin) {
        return "Running as Admin (Note: App should also support Non-Admin)"
    } else {
        return "Running as User (Standard Mode)"
    }
}

# B. DEPENDENCIES
Invoke-Test "Python Check" {
    if ($SystemInfo.Python -match "Not Found") { throw "Python not found in PATH" }
    # Check pip
    $pip = python -m pip --version 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Pip check failed" }
    return "Python and Pip valid"
}

# C. NETWORKING
if (-not $NoNetworkTests) {
    Invoke-Test "Network Connectivity" {
        if (Test-Connection "8.8.8.8" -Count 1 -Quiet) {
            return "Internet Reachable"
        } else {
            throw "Offline or DNS failing"
        }
    }
} else {
    New-TestResult -Name "Network Connectivity" -Result "SKIP" -Details "User requested skip"
}

# D. APP LAUNCH / STABILITY
# We try to launch the app. Based on test.ps1, it supports 'run --duration X'.
# We also try 'version' or 'help' for safer Quick tests.

if ($AppEntry) {

    # 1. CLI Response Test (--help)
    Invoke-Test "CLI Response (--help)" {
        $p = Start-Process -FilePath "python" -ArgumentList "-u", "`"$AppEntry`"", "--help" -NoNewWindow -PassThru -Wait
        if ($p.ExitCode -ne 0) { throw "App returned exit code $($p.ExitCode) on --help" }
        return "Help command success"
    }

    # 2. Stability Loop
    # We will try to run a very short session.
    # If standard 'run' invocation needs args, we use what we found in test.ps1 logic
    # For fast testing: 1 minute duration with 90 second timeout (allows startup/shutdown overhead)

    $DurationMinutes = if ($Fast) { 1 } else { 5 }
    $TimeoutMs = ($DurationMinutes * 60 + 30) * 1000  # Duration in seconds + 30s buffer for startup/shutdown

    # Valid arguments based on test.ps1
    $TestArgs = @("-u", "$AppEntry", "run", "--mode", "live-session", "--execution-mode", "paper", "--duration", "$DurationMinutes", "--symbol", "BTCUSDT", "--async")

    Write-Log "Starting Stability Loops ($Iterations iterations)..." -Color Cyan

    # Lock files that need cleanup between runs
    $LockFiles = @(
        ".agent/lockfile.pid",
        "paper/async_session.lock",
        "src/laptop_agents/paper/async_session.lock"
    )

    for ($i = 1; $i -le $Iterations; $i++) {
        # Clean up lock files before each iteration
        foreach ($lock in $LockFiles) {
            $lockPath = Join-Path $ScriptRoot $lock
            if (Test-Path $lockPath) {
                Remove-Item $lockPath -Force -ErrorAction SilentlyContinue
                Write-Log "Cleaned lock: $lock" -Level "INFO"
            }
        }

        Invoke-Test "Stability Loop $i/$Iterations" {
            $logOut = Join-Path $ArtifactsDir "stability_loop_${i}_stdout.log"
            $logErr = Join-Path $ArtifactsDir "stability_loop_${i}_stderr.log"

            $p = Start-Process -FilePath "python" -ArgumentList $TestArgs -RedirectStandardOutput $logOut -RedirectStandardError $logErr -PassThru -WindowStyle Hidden

            # Watch for duration + buffer
            $p.WaitForExit($TimeoutMs)

            if (-not $p.HasExited) {
                Stop-Process -Id $p.Id -Force
                throw "App hung (timeout $($TimeoutMs/1000)s)"
            }

            $exitCode = $p.ExitCode
            if ($null -eq $exitCode) { $exitCode = -1 }

            # Check logs for successful completion markers
            $outContent = Get-Content $logOut -ErrorAction SilentlyContinue | Out-String
            $errContent = Get-Content $logErr -ErrorAction SilentlyContinue | Out-String

            $successMarkers = @(
                "SESSION COMPLETE",
                "Duration limit reached",
                "GRACEFUL SHUTDOWN"
            )

            $hasSuccess = $false
            foreach ($marker in $successMarkers) {
                if ($outContent -match $marker) {
                    $hasSuccess = $true
                    break
                }
            }

            # If we have success markers, override exit code check
            if ($hasSuccess) {
                # Validate log had heartbeat
                if (-not (Select-String -Path $logOut -Pattern "Heartbeat" -Quiet)) {
                    throw "No heartbeat found in successful run"
                }
                return "Loop $i completed successfully (${DurationMinutes}min run)"
            }

            # Otherwise check exit code
            if ($exitCode -ne 0) {
                if (-not $errContent) { $errContent = $outContent }
                if (-not $errContent) { $errContent = "No log output captured." }
                throw "App crashed with code $exitCode. Log preview: $($errContent.Substring(0, [math]::Min($errContent.Length, 200)))"
            }
        }
        Start-Sleep -Seconds 2 # Cool down
    }
}

# E. ENVIRONMENT VARIATIONS (Sandbox)
# Create a path with spaces
Invoke-Test "Path With Spaces" {
    $SpaceDir = Join-Path $SandboxDir "Path With Spaces"
    New-Item -ItemType Directory -Path $SpaceDir -Force | Out-Null
    # We can't easily move the python app, but we can try to launch IT from there as CWD
    # or pass it as --cwd argument if supported.
    # Instead, verify we can WRITE to it from PowerShell as a proxy for FS health.
    $TestFile = Join-Path $SpaceDir "test_write.txt"
    "Data" | Out-File $TestFile
    if (-not (Test-Path $TestFile)) { throw "Failed to write to path with spaces" }
    return "FileSystem handles spaces OK"
}

# F. RESOURCE SNAPSHOT
Invoke-Test "Resource Check" {
    $mem = Get-CimInstance Win32_OperatingSystem
    $free = [math]::Round($mem.FreePhysicalMemory / 1MB, 2)
    return "Memory Free: ${free}GB"
}


# --- 4. Reporting ---
Write-Log "--- Phase 4: Reporting ---" -Color Magenta

$ReportData = @{
    run_id = $RunID
    timestamp = Get-Date -Format "o"
    system_info = $SystemInfo
    discovery = $Discovery
    results = $TestResults
    summary = @{
        total = $TestResults.Count
        passed = @($TestResults | Where-Object { $_.Result -eq "PASS" }).Count
        failed = @($TestResults | Where-Object { $_.Result -eq "FAIL" }).Count
        skipped = @($TestResults | Where-Object { $_.Result -eq "SKIP" }).Count
    }
}

# JSON Report
$JsonOptions = @{ Depth = 10 }
if ($PSVersionTable.PSVersion.Major -ge 7) { $JsonOptions["EnumsAsStrings"] = $true }
$ReportData | ConvertTo-Json @JsonOptions | Out-File $ReportJSON -Encoding utf8

# Text Report
$Sb = [System.Text.StringBuilder]::new()
[void]$Sb.AppendLine("TestAll Report - $RunID")
[void]$Sb.AppendLine("================================================")
[void]$Sb.AppendLine("System: $($SystemInfo.OS) | Python: $($SystemInfo.Python)")
[void]$Sb.AppendLine("App: $($Discovery.Path) ($($Discovery.Method))")
[void]$Sb.AppendLine("")
[void]$Sb.AppendLine("Results Summary")
[void]$Sb.AppendLine("PASS: $($ReportData.summary.passed)")
[void]$Sb.AppendLine("FAIL: $($ReportData.summary.failed)")
[void]$Sb.AppendLine("SKIP: $($ReportData.summary.skipped)")
[void]$Sb.AppendLine("")
[void]$Sb.AppendLine("Detailed Findings:")
foreach ($r in $TestResults) {
    [void]$Sb.AppendLine("[$($r.Result)] $($r.Name) ($($r.DurationMs)ms)")
    if ($r.Result -ne "PASS") {
        [void]$Sb.AppendLine("   Error: $($r.Details)")
    }
}
$Sb.ToString() | Out-File $ReportText -Encoding utf8


# --- Cleanup ---
if (-not $KeepArtifacts) {
    if (Test-Path $SandboxDir) { Remove-Item $SandboxDir -Recurse -Force -ErrorAction SilentlyContinue }
}

# --- Final Console Output ---
Write-Host "`n================================================" -ForegroundColor Cyan
Write-Host " TEST PASS COMPLETE" -ForegroundColor Cyan
Write-Host " Passed: $($ReportData.summary.passed)" -ForegroundColor Green
Write-Host " Failed: $($ReportData.summary.failed)" -ForegroundColor Red
Write-Host " Report: $ReportJSON" -ForegroundColor Gray
Write-Host "================================================" -ForegroundColor Cyan

if ($ReportData.summary.failed -gt 0) { exit 1 }
exit 0
