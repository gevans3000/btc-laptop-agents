# testall.ps1 - Usage Guide

## Overview
`testall.ps1` is a comprehensive Windows QA automation script that performs exhaustive testing of your trading application. It automatically discovers the app, runs a full test matrix, and produces AI-friendly diagnostic reports.

## Quick Start

```powershell
# Fast mode (1 minute stability test, 1 iteration)
.\testall.ps1 -Fast

# Standard mode (5 minute stability test, 5 iterations)
.\testall.ps1

# Custom iterations
.\testall.ps1 -Iterations 10

# Keep artifacts for debugging
.\testall.ps1 -KeepArtifacts -VerboseLogs
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `-Iterations` | int | 5 | Number of stability loop iterations |
| `-KeepArtifacts` | switch | false | Preserve sandbox/logs even on success |
| `-VerboseLogs` | switch | false | Enable detailed console logging |
| `-AppPathOverride` | string | (auto) | Manual app entry point override |
| `-NoNetworkTests` | switch | false | Skip connectivity checks |
| `-Fast` | switch | false | Quick mode: 1 iteration, 1-minute runs |

## Test Matrix

The script runs the following tests:

### 1. System & Environment
- ✅ Permission level detection (Admin/User)
- ✅ Python version validation (≥3.10)
- ✅ Virtual environment check
- ✅ Dependency integrity (`pip check`)
- ✅ Configuration file validation (`.env`)
- ✅ Stale lockfile cleanup
- ✅ System resource snapshot (RAM, CPU)

### 2. Network Connectivity
- ✅ Internet reachability test
- ⏭️ Skippable with `-NoNetworkTests`

### 3. Application Tests
- ✅ CLI response (`--help`)
- ✅ Stability loops (configurable iterations)
  - Runs app for specified duration (1 min fast, 5 min standard)
  - Monitors for crashes, hangs, and errors
  - Validates heartbeat activity
  - Checks for graceful shutdown

### 4. File System
- ✅ Path with spaces handling
- ✅ Resource availability check

## Output Artifacts

All artifacts are saved to `._testall_artifacts\<timestamp>\`:

- **testall-report.json** - Machine-readable report for AI analysis
- **testall-report.txt** - Human-readable summary
- **stability_loop_N_stdout.log** - Per-iteration stdout logs
- **stability_loop_N_stderr.log** - Per-iteration stderr logs
- **testall.log** - Main script execution log

## Report Structure

### JSON Report (`testall-report.json`)
```json
{
  "run_id": "20260117-144658",
  "timestamp": "2026-01-17T14:46:58-05:00",
  "system_info": {
    "OS": "Microsoft Windows 11 Pro",
    "Architecture": "AMD64",
    "Python": "Python 3.12.7",
    "IsAdmin": false,
    ...
  },
  "discovery": {
    "Path": "C:\\...\\main.py",
    "Method": "Parsed test.ps1",
    "Type": "Python"
  },
  "results": [
    {
      "pId": 1,
      "Name": "Permission Check",
      "Result": "PASS",
      "DurationMs": 13,
      "Details": "Running as User (Standard Mode)",
      "Timestamp": "2026-01-17T14:46:59-05:00"
    },
    ...
  ],
  "summary": {
    "total": 7,
    "passed": 7,
    "failed": 0,
    "skipped": 0
  }
}
```

### Text Report (`testall-report.txt`)
Simple, grep-friendly format with:
- System info
- App discovery method
- Pass/Fail/Skip counts
- Detailed findings with timing

## Exit Codes

- **0** - All tests passed
- **1** - One or more tests failed

## App Discovery Strategy

The script uses a three-tier discovery approach:

1. **Override** - If `-AppPathOverride` is provided
2. **Parse test.ps1** - Extracts app path from existing test script
3. **File Scan** - Searches for `main.py`, `app.py`, `start.ps1`

## Stability Test Logic

For each iteration:
1. Clean up stale lock files
2. Launch app with `--duration N --execution-mode paper --async`
3. Wait for completion (duration + 30s buffer)
4. Check logs for success markers:
   - "SESSION COMPLETE"
   - "Duration limit reached"
   - "GRACEFUL SHUTDOWN"
5. Validate heartbeat activity
6. Mark PASS/FAIL based on log analysis

## Troubleshooting

### "App hung (timeout Xs)"
- App didn't complete within expected time
- Check `stability_loop_N_stdout.log` for where it stopped
- Increase timeout by using longer duration

### "App crashed with code -1"
- Check stderr log for exceptions
- Verify `.env` configuration
- Ensure no conflicting processes

### "No heartbeat found"
- App started but didn't produce expected log output
- Check if app is using correct logging format

## Integration with CI/CD

```powershell
# Example CI script
.\testall.ps1 -Fast -NoNetworkTests
if ($LASTEXITCODE -ne 0) {
    Write-Error "Tests failed"
    exit 1
}
```

## AI-Friendly Features

- Structured JSON output for programmatic analysis
- Timestamped artifacts for historical tracking
- Log snippets included in failure reports
- Success markers for semantic analysis
- Detailed system context for reproducibility
