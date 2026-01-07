# BTC Laptop Agents - Paper Trading MVP

This is a local-only, laptop-run paper trading system for Bitcoin trading simulation. It executes trades against mock market data and generates performance reports. No real money, no APIs, no cloud services.

## MVP Contract (Read This First)

This MVP is intentionally frozen. The main branch contains only the minimal viable product:
- 5 commands: verify, run once, start live, status, stop
- Mock data only (no external APIs)
- Local PowerShell execution
- Paper trading (simulated, no real money)

Future work belongs in feature branches, not main. This contract ensures stability.

## What This System Does

- Simulates Bitcoin trading using mock market data
- Runs locally on your Windows laptop
- Generates HTML reports and CSV exports
- Tracks paper trading performance over time
- Operates unattended (safe for overnight runs)

## What This System Does NOT Do

- No real trading (paper only)
- No OpenAI API calls
- No cloud services
- No live market data (mock only)
- No automated strategy optimization
- No backtesting beyond basic validation

## Quick Start (5 minutes)

```powershell
# 1. Verify system integrity
.\[scripts](scripts/verify.ps1) -Mode quick

# 2. Run one trade cycle and view results
.\[scripts](scripts/mvp_run_once.ps1)

# 3. Start background paper trading
.\[scripts](scripts/mvp_start_live.ps1)

# 4. Check status anytime
.\[scripts](scripts/mvp_status.ps1)

# 5. Stop when done
.\[scripts](scripts/mvp_stop_live.ps1)
```

## Daily Use

### Run Once
```powershell
.\[scripts](scripts/mvp_run_once.ps1)
```

### Start Background Loop
```powershell
.\[scripts](scripts/mvp_start_live.ps1)
```

### Check Status
```powershell
.\[scripts](scripts/mvp_status.ps1)
```

### Stop Background Process
```powershell
.\[scripts](scripts/mvp_stop_live.ps1)
```

### Open Latest Report
```powershell
.\[scripts](scripts/mvp_open.ps1)
```

## How to Confirm EVERYTHING is OFF

```powershell
# Method 1: Use status script
.\[scripts](scripts/mvp_status.ps1)
# Should show: OFF

# Method 2: Manual PowerShell check
Get-Process python | Where-Object { $_.MainWindowTitle -like 'run.py' }
# Should return nothing

# Method 3: Check PID file
Test-Path paper\mvp.pid
# Should return False
```

## Outputs

All generated files live in these directories (gitignored):

- `runs/latest/summary.html` - HTML report with trades and equity curve
- `runs/latest/events.jsonl` - JSON Lines event log
- `runs/latest/trades.csv` - Trade history in CSV format
- `paper/mvp.pid` - Process ID file (when running)
- `paper/live.out.txt` - Standard output log
- `paper/live.err.txt` - Error log
- `paper/events.jsonl` - Live trading events
- `paper/trades.csv` - Accumulated trade history
- `paper/state.json` - Persistent trading state

## Troubleshooting

### summary.html missing

Run a trade cycle first:
```powershell
.\[scripts](scripts/mvp_run_once.ps1)
```

### Process appears stuck

1. Check status:
```powershell
.\[scripts](scripts/mvp_status.ps1)
```

2. If STALE, clean up:
```powershell
.\[scripts](scripts/mvp_stop_live.ps1)
```

### Status shows STALE

This means the PID file exists but the process isn't running. Safe to clean up:
```powershell
.\[scripts](scripts/mvp_stop_live.ps1)
```

### verify.ps1 fails

Check the specific error message. Common fixes:

- **Compilation failed**: Run `python -m compileall src`
- **Selftest failed**: This indicates a logic error - check the error details
- **Missing files**: Run `mvp_run_once.ps1` first to generate outputs

### No events or trades

Ensure you have run a trade cycle or started the background process. If the issue persists, check the logs in `paper/live.out.txt` and `paper/live.err.txt`.

## Architecture (1 minute)

The system follows a simple pipeline:

1. **Data Source**: Mock data generator (no external APIs)
2. **Strategy**: SMA(10/30) crossover signals
3. **Risk Engine**: Position sizing, stop-loss, take-profit
4. **Execution**: Simulated trades with slippage and fees
5. **Outputs**: HTML reports, CSV exports, JSONL event logs

## Release Discipline

### How to Commit

1. Ensure all changes are tested and verified
2. Update documentation to reflect changes
3. Commit with a clear, descriptive message

### When to Tag v1.0.0

Tag v1.0.0 after:
- All MVP features are working
- Documentation is complete and accurate
- Tests pass successfully
- Code review is approved

## Requirements

- Windows 10/11
- PowerShell 5+
- Python 3.12+ (venv recommended)
- No cloud services
- No API keys required

## Assumptions

- You've already created the venv: `python -m venv .venv`
- Dependencies installed: `pip install -r requirements.txt`
- Running from repo root: `cd c:\path\to\btc-laptop-agents`
- No admin privileges needed

## MVP Completeness Checklist

- [x] 5 core commands working (verify, run once, start, status, stop)
- [x] Mock data only (no external APIs)
- [x] Local PowerShell execution
- [x] Paper trading simulation
- [x] HTML reports generated
- [x] PID file management
- [x] Stale process handling
- [x] Atomic file writes
- [x] Background process support
- [x] Comprehensive README

This MVP is complete and frozen. No additional features will be added to main.
