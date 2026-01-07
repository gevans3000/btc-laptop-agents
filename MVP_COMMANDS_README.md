# BTC Laptop Agents - MVP Control Surface

## MVP Control Surface - 6 Key Commands

These 6 commands provide complete control over the paper trading system:

```powershell
# 1. VERIFY - Check system integrity (quick mode)
.\scripts\verify.ps1 -Mode quick

# 2. RUN ONCE - Execute one live tick and show results
.\scripts\mvp_run_once.ps1

# 3. START LIVE - Begin background paper trading
.\scripts\mvp_start_live.ps1

# 4. STATUS - Check running status and recent events
.\scripts\mvp_status.ps1

# 5. STOP LIVE - Stop the background trading process
.\scripts\mvp_stop_live.ps1

# Bonus: OPEN - View latest results in browser
.\scripts\mvp_open.ps1
```

## Full Command Reference

### Core Trading Commands
```bash
# Single trade simulation (original behavior)
python -m src.laptop_agents.run --source mock --symbol BTCUSDT

# Backtest with position management
python -m src.laptop_agents.run --mode backtest --source mock --limit 500 --backtest 500

# Live paper trading (foreground)
python -m src.laptop_agents.run --mode live --source mock --symbol BTCUSDT --interval 1m

# Validation with parameter grid
python -m src.laptop_agents.run --mode validate --source mock --limit 2000 --grid "sma=10,30;stop=20,30;tp=1.0,1.5"

# Self-test (deterministic verification)
python -m src.laptop_agents.run --mode selftest --intrabar-mode conservative
```

### Advanced Options
```bash
# Risk management parameters
python -m src.laptop_agents.run --mode backtest --risk-pct 1.0 --stop-bps 30.0 --tp-r 1.5 --max-leverage 1.0

# Intrabar mode (conservative vs optimistic)
python -m src.laptop_agents.run --mode backtest --intrabar-mode optimistic

# Validation parameters
python -m src.laptop_agents.run --mode validate --validate-splits 5 --validate-train 600 --validate-test 200

# Backtest mode selection
python -m src.laptop_agents.run --mode backtest --backtest-mode bar  # Simple bar-by-bar
python -m src.laptop_agents.run --mode backtest --backtest-mode position  # Position management
```

### Data Source Options
```bash
# Mock data (default, no API needed)
python -m src.laptop_agents.run --source mock

# Bitunix futures (requires API keys)
python -m src.laptop_agents.run --source bitunix --symbol BTCUSDT --interval 1m
```

## Output Files

### Standard Outputs (always generated)
- `runs/latest/summary.html` - HTML report with trades, equity curve, and statistics
- `runs/latest/trades.csv` - All trades in CSV format
- `runs/latest/events.jsonl` - Event log in JSON Lines format
- `runs/latest/state.json` - Final state and configuration

### Live Paper Trading Outputs
- `paper/state.json` - Persistent trading state
- `paper/trades.csv` - Accumulated trade history
- `paper/events.jsonl` - Live event log
- `paper/live.pid` - Process ID file (when running)
- `paper/live.out.txt` - Standard output log
- `paper/live.err.txt` - Error log

### Validation Outputs
- `runs/latest/validation.json` - Comprehensive validation report
- `runs/latest/validate_folds.csv` - Per-fold validation results
- `runs/latest/validate_results.json` - Full validation data

## Capabilities

### Trading Modes
- **single**: One trade simulation (default)
- **backtest**: Historical backtesting with position management
- **live**: Paper trading with persistent state
- **validate**: Walk-forward validation with parameter grid
- **selftest**: Deterministic verification of risk engine

### Risk Management
- Position sizing based on % risk per trade
- Stop loss and take profit calculation
- Maximum leverage constraints
- Conservative vs optimistic intrabar execution

### Analysis Features
- Equity curve visualization
- Win rate and profit factor calculation
- Maximum drawdown tracking
- Parameter grid optimization
- Walk-forward validation

### Data Sources

The system supports two data sources:

- **Mock data** (default, no API needed): Simulated market data for testing
- **Bitunix futures** (optional): Real market data requiring API keys

For Bitunix mode, configure your API keys in `.env` file:

```
BITUNIX_API_KEY=your_api_key
BITUNIX_API_SECRET=your_api_secret
```
## Configuration

### Environment Variables
Create `.env` file (ignored by git):
```
# Bitunix API keys (if using bitunix source)
BITUNIX_API_KEY=your_api_key
BITUNIX_API_SECRET=your_api_secret
```

### Default Parameters
- Starting balance: $10,000
- Fees: 2 bps (0.02%) per side
- Slippage: 0.5 bps (0.005%)
- Risk per trade: 1.0%
- Stop distance: 30 bps (0.30%)
- TP ratio: 1.5 (1.5:1 reward:risk)
- Max leverage: 1.0x
- Intrabar mode: conservative

## Troubleshooting

### Check if live process is running
```powershell
# Using MVP status script
.\scripts\mvp_status.ps1

# Manual PowerShell check
Get-Process python | Where-Object { $_.MainWindowTitle -like 'run.py' }
```

### Verify file outputs
```powershell
# Check latest run
Test-Path runs\latest\summary.html

# Check live state
Test-Path paper\state.json
```

### Clean up
```powershell
# Remove all generated files (safe - they're in .gitignore)
Remove-Item -Recurse -Force runs, paper
```

## Best Practices

1. **Always verify first**: Run `verify.ps1` before trading
2. **Start with mock data**: Test with `--source mock` before using real APIs
3. **Check status frequently**: Use `mvp_status.ps1` to monitor
4. **Review results**: Always open `summary.html` after runs
5. **Use conservative settings**: Start with low risk percentages

## Command Cheat Sheet

| Command | Description |
|---------|-------------|
| `mvp_status.ps1` | Show system status and recent events |
| `mvp_start_live.ps1` | Start live paper trading |
| `mvp_stop_live.ps1` | Stop live paper trading |
| `mvp_run_once.ps1` | Run one cycle and view results |
| `mvp_open.ps1` | Open latest summary report |
| `verify.ps1` | Verify system integrity |
| `python -m src.laptop_agents.run --help` | Show all CLI options |