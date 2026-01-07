# BTC Laptop Agents - AI Handoff

This document provides essential context for AI assistants working with the BTC Laptop Agents project.

## Project Intent + MVP Contract

The project is a minimal, local-only paper trading system for Bitcoin trading simulation. The MVP contract ensures:
- Only 5 core commands are supported (verify, run once, start live, status, stop)
- Mock data only (no external APIs)
- Local PowerShell execution
- Paper trading (simulated, no real money)

**Ground Rules:**
- No API costs unless explicitly approved
- Keep outputs gitignored
- Favor PowerShell automation
- No scope expansion on main branch

## Where to Look First for Truth

1. **Scripts Directory**: [`scripts/`](scripts/) contains all MVP control scripts
2. **CLI Help**: [`src/laptop_agents/run.py`](src/laptop_agents/run.py) provides CLI options
3. **Outputs**: `runs/latest/summary.html` and `paper/events.jsonl`
4. **Configuration**: `.env.example` for environment variables

## Assistant Sync Pack

To generate and paste the assistant sync pack:

```powershell
.\[scripts](scripts/make_sync_pack.ps1)
```

This script generates `assistant_sync_pack.md` containing:
- Git status
- Key file hashes
- Last run snapshot
- System configuration

## Known Sharp Edges

1. **Candle Order Reversal**: Some data providers return candles in newest-first order. The system automatically detects and reverses this.
2. **Validate Mode Requirements**: Ensure you have enough candles for validation splits (train + splits*test).
3. **PID File Management**: Always use the provided scripts to manage the background process to avoid stale PID files.
4. **Atomic File Writes**: The system uses atomic writes for all output files to prevent corruption.

## Command Reference

| Command | Purpose | Logs | PID File |
|---------|---------|------|----------|
| `verify.ps1 -Mode quick` | System integrity check | N/A | N/A |
| `mvp_run_once.ps1` | Single trade cycle + report | `paper/live.out.txt` | N/A |
| `mvp_start_live.ps1` | Background paper trading | `paper/live.out.txt` | `paper/mvp.pid` |
| `mvp_status.ps1` | Show running status + events | N/A | N/A |
| `mvp_stop_live.ps1` | Stop background process | N/A | Removes `paper/mvp.pid` |
| `mvp_open.ps1` | Open latest report | N/A | N/A |

## Troubleshooting for AI

### Missing summary.html
Run a trade cycle first:
```powershell
.\[scripts](scripts/mvp_run_once.ps1)
```

### Stale PID File
Clean up using:
```powershell
.\[scripts](scripts/mvp_stop_live.ps1)
```

### Verify Failures
Check the specific error message and refer to the troubleshooting section in [`README.md`](README.md).

### No Events or Trades
Ensure the background process is running and check logs in `paper/live.out.txt` and `paper/live.err.txt`.

## Best Practices

1. Always verify first: Run `verify.ps1` before trading
2. Start with mock data: Test with `--source mock` before using real APIs
3. Check status frequently: Use `mvp_status.ps1` to monitor
4. Review results: Always open `summary.html` after runs
5. Use conservative settings: Start with low risk percentages