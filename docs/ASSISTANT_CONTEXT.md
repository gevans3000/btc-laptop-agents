# BTC Laptop Agents - Assistant Context

This project provides a minimal, local-only framework for running trading agents on your laptop. It focuses on simplicity, Windows PowerShell compatibility, and generating compact sync packs to keep AI assistants in sync under token limits.

## Current Working Definition of Done
- Mock and Bitunix data sources work
- Single-bar trade simulation with SMA(10/30) signals
- Outputs: `runs/latest/{summary.html, events.jsonl, trades.csv, state.json}`
- PowerShell scripts for local execution

## Exact Commands to Run

### Mock run (fast, no API):
```powershell
.\.venv\Scripts\python.exe -m laptop_agents.run --source mock
```

### Bitunix run (real data):
```powershell
.\.venv\Scripts\python.exe -m laptop_agents.run --source bitunix --symbol BTCUSDT --interval 1m --limit 200
```

### Open HTML report:
```powershell
Start-Process (Resolve-Path .\runs\latest\summary.html)
```

## Where Outputs Live
All run artifacts are stored in `runs/latest/`:
- `summary.html` - Human-readable run summary
- `events.jsonl` - Event stream (one JSON object per line)
- `trades.csv` - Trade records
- `state.json` - Final state snapshot

## Ground Rules for Changes
1. **Bare-bones first**: Prioritize minimal working solutions
2. **Avoid refactors**: Only modify what's necessary for the current task
3. **Windows PowerShell**: All scripts must work in Windows PowerShell
4. **No external dependencies**: Use only Git and PowerShell

## Known Pitfalls
- **Conda vs venv**: Always use `.venv\Scripts\python.exe`, not Conda Python
- **Path issues**: Use `Resolve-Path` for reliable path resolution in PowerShell
- **Large diffs**: Truncate file diffs to avoid bloating sync packs
- **Missing runs/latest**: Handle gracefully when directory doesn't exist
- **Git status**: Use `--porcelain` format for machine-readable output