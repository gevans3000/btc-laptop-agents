# RUNBOOK.md — Operations Manual

> **Scope**: The authoritative guide for operating the BTC Laptop Agents MVP.
> **Audience**: Humans and Agents.

## 1. Quick Reference

| Action | Script | Expected Output |
| :--- | :--- | :--- |
| **Start** | `.\scripts\mvp_start_live.ps1` | `Live paper trading started with PID 12345` |
| **Stop** | `.\scripts\mvp_stop_live.ps1` | `Process 12345 stopped` |
| **Status** | `.\scripts\mvp_status.ps1` | `Status: RUNNING` or `OFF` |
| **Run Once** | `.\scripts\mvp_run_once.ps1` | Generates `runs/latest/summary.html` |
| **View** | `.\scripts\mvp_open.ps1` | Opens default browser to summary |
| **Verify** | `.\scripts\verify.ps1` | `VERIFY: PASS` |

## 2. Detailed Procedures

### A. Start Live Trading (Daemon)
**Command**: `.\scripts\mvp_start_live.ps1`
*   **What it does**: Checks for existing PID. Starts `run.py --mode live` in background (hidden window). Writes PID to `paper/mvp.pid`. Redirects logs to `paper/live.out.txt`.
*   **Verification**: Run `.\scripts\mvp_status.ps1` immediately after. It should say "RUNNING".

### B. Stop Live Trading
**Command**: `.\scripts\mvp_stop_live.ps1`
*   **What it does**: Reads PID from `paper/mvp.pid`. Kills the process. Removes the PID file.
*   **Note**: This is a hard kill. The system is designed to handle this safely (atomic table writes).

### C. Check Status
**Command**: `.\scripts\mvp_status.ps1`
*   **Output meanings**:
    *   **RUNNING**: Process exists and PID file exists.
    *   **OFF**: No PID file.
    *   **STALE**: PID file exists, but process is gone. (Script will offer to clean up).
*   **Logs**: Displays the last 10 lines of `paper/events.jsonl`.

### D. Recovery (Stale PID)
If status says **STALE**:
1. Run `.\scripts\mvp_stop_live.ps1` to clean the orphan PID file.
2. Check `paper/live.err.txt` for crash reasons.
3. Run `.\scripts\verify.ps1` to ensure code integrity.
4. Restart with `.\scripts\mvp_start_live.ps1`.

### E. Manual Verification
To confirm "OFF" status manually:
```powershell
Get-Process python | Where-Object { $_.MainWindowTitle -like '*run.py*' }
# Should return nothing
Test-Path paper\mvp.pid
# Should return False
```

## 3. Logs & Artifacts

All live artifacts are in the `paper/` directory (gitignored):
*   `live.out.txt`: Stdout capture.
*   `live.err.txt`: Stderr capture (check here for crashes).
*   `events.jsonl`: Structured event log.
*   `trades.csv`: Record of all paper trades.
*   `state.json`: Current positions and balance.

## 4. Updates & Maintenance
Before applying any code update:
1. **Stop** the live runner: `.\scripts\mvp_stop_live.ps1`
2. **Pull/Edit** code.
3. **Verify**: `.\scripts\verify.ps1 -Mode quick`
4. **Start**: `.\scripts\mvp_start_live.ps1`

## 5. Backtesting

Run historical simulations to test strategy performance.

### A. Basic Backtest Commands

*   **Position Mode (Default - Recommended)**:
    ```powershell
    python -m src.laptop_agents.run --mode backtest --backtest 500
    ```
    Uses risk-based position sizing with stop-loss and take-profit management.

*   **Bar Mode (Simple)**:
    ```powershell
    python -m src.laptop_agents.run --mode backtest --backtest 500 --backtest-mode bar
    ```
    One trade per bar, simpler logic.

### B. Backtest with Real Data (Bitunix)

*   **Backtest on Bitunix Historical Data**:
    ```powershell
    python -m src.laptop_agents.run --mode backtest --source bitunix --symbol BTCUSD --interval 5m --backtest 1000
    ```

### C. Risk Parameters

Customize risk management settings:

```powershell
python -m src.laptop_agents.run --mode backtest --backtest 500 \
  --risk-pct 1.0 \
  --stop-bps 30.0 \
  --tp-r 1.5 \
  --max-leverage 1.0 \
  --intrabar-mode conservative
```

**Parameters**:
- `--risk-pct`: % of equity risked per trade (default: 1.0)
- `--stop-bps`: Stop distance in basis points (default: 30.0 = 0.30%)
- `--tp-r`: Take profit ratio (default: 1.5 = 1.5x stop distance)
- `--max-leverage`: Maximum leverage (default: 1.0 = no leverage)
- `--intrabar-mode`: `conservative` (stop first) or `optimistic` (TP first)

### D. Outputs

All backtest results are saved to `runs/latest/`:
- `summary.html`: Interactive dashboard with charts
- `trades.csv`: All trade details
- `equity.csv`: Equity curve data
- `stats.json`: Performance metrics
- `events.jsonl`: Event log

**View Results**:
```powershell
.\scripts\mvp_open.ps1
```

## 6. Live & Shadow Trading (Bitunix)

The `bitunix_cli.py` tool allows for controlled live trading sessions.

### A. Shadow Mode (Safe Simulation)
Simulates trades with **real live data** but **does not execute orders**.

*   **Quick Connectivity Check (5 mins)**:
    ```powershell
    python -m laptop_agents.bitunix_cli live-session --symbol BTCUSD --interval 1m --duration-min 5
    ```
*   **Standard Session (1 hour)**:
    ```powershell
    python -m laptop_agents.bitunix_cli live-session --symbol BTCUSD --interval 1m --duration-min 60
    ```
*   **USDT Futures**:
    ```powershell
    python -m laptop_agents.bitunix_cli live-session --symbol BTCUSDT --interval 1m --duration-min 60
    ```

### B. Live Trading (Real Money ⚠️)
**WARNING**: This executes real orders on your Bitunix account. Use with caution.

*   **Command**:
    ```powershell
    python -m laptop_agents.bitunix_cli live-session --symbol BTCUSD --interval 1m --duration-min 60 --no-shadow
    ```
