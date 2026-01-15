# RUNBOOK.md — Operations Manual

> **Status**: ACTIVE

> **Scope**: The authoritative guide for operating the BTC Laptop Agents MVP.
> **Audience**: Humans and Agents.

## 1. Quick Reference

| Action | Script | Expected Output |
| :--- | :--- | :--- |
| **Verify System** | `.\scripts\verify.ps1` | `VERIFY: PASS` |
| **Pre-Commit Check** | `/pre-commit` (or `python scripts/verify.ps1`) | Ensures code quality. |
| **Start Live Dashboard** | `.\scripts\live_dashboard.ps1` | Interactive UI on `http://localhost:5000` |
| **Monitor Health** | `python scripts/monitor_heartbeat.py` | Alerts if process freezes (>5s stale). |
| **Backtest** | `python -m src.laptop_agents.run --mode backtest` | Results in `runs/latest/` |
| **Emergency Stop**| `Edit config/KILL_SWITCH.txt -> TRUE` | Blocks all order submissions. |

## 2. Prerequisites & Setup

### A. Environment
- **Python**: 3.10 or higher.
- **Dependencies**: Install via `pip install -e .` from the repo root.
- **API Keys**: Create a `.env` file in the root directory:
  ```env
  BITUNIX_API_KEY=your_key_here
  BITUNIX_API_SECRET=your_secret_here
  ```

### B. Verification
Before running any live code, ALWAYS run the pre-commit checks:
```powershell
# Using the AI agent workflow
/pre-commit

# Or manually
python -m pytest tests/ -q
python scripts/verify.ps1
```

## 3. Operational Modes

The system primarily runs through `src/laptop_agents/run.py`.

### A. Live Session (Autonomous)
This is the standard mode for running the agent for a fixed duration with high-performance async engine.

- **Paper Trading (10 mins)**:
  ```powershell
  $env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session --source bitunix --symbol BTCUSD --execution-mode paper --duration 10 --async --dashboard
  ```

- **Live Trading (REAL MONEY)**:
  Requires manual confirmation unless `SKIP_LIVE_CONFIRM=TRUE`.
  ```powershell
  $env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session --source bitunix --symbol BTCUSD --execution-mode live --duration 60 --async --dashboard
  ```

### B. Orchestrated Sim (Dev)
Test the agent stack with mock data:
```powershell
python -m src.laptop_agents.run --mode orchestrated --source mock
```

### C. Stress Testing
Verify system stability under load:
```powershell
python tests/stress/test_high_load.py
```

### D. Checking Status & Recovery
If the watchdog is running, you can monitor the system via:
1. **The Dashboard**: `.\scripts\dashboard_up.ps1`
2. **The Logs**: `Get-Content logs/system.jsonl -Wait`
3. **Recovery**: To stop the watchdog, press `Ctrl+C` in its terminal window. If a process is stuck, the watchdog will attempt to kill and restart it every 10 seconds.

### D. Manual Verification
To confirm "OFF" status manually:
```powershell
Get-Process python | Where-Object { $_.MainWindowTitle -like '*run.py*' }
# Should return nothing
Test-Path paper\mvp.pid
# Should return False
```

## 4. Logs & Artifacts

The system produces artifacts in two locations depending on the mode:

### A. Orchestrated Mode (Recommended)
Artifacts are saved in `runs/<id>/` and the latest run is symlinked to `runs/latest/`.
- `runs/latest/summary.html`: Interactive dashboard.
- `runs/latest/trades.csv`: Detailed trade log.
- `runs/latest/events.jsonl`: Orchestration step log.

### B. Machine/System Logs
- `logs/system.jsonl`: Every system event, including errors and latencies.
- `logs/watchdog.log`: Logs from the process supervisor.

### C. Legacy Mode (Paper)
If using the old `--mode live`, artifacts are in `paper/`:
- `paper/events.jsonl`
- `paper/trades.csv`
- `paper/state.json`

## 5. Updates & Maintenance
Before applying any code update:
1. **Stop** the watchdog (`Ctrl+C`).
2. **Pull/Edit** code.
3. **Verify**: `.\scripts\verify.ps1`
4. **Restart**: `.\scripts\watchdog.ps1 ...`

## 6. Backtesting

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
  --max_leverage 1.0 \
  --intrabar-mode conservative
```

**Parameters**:
- `--risk-pct`: % of equity risked per trade (default: 1.0)
- `--stop-bps`: Stop distance in basis points (default: 30.0 = 0.30%)
- `--tp-r`: Take profit ratio (default: 1.5 = 1.5x stop distance)
- `--max_leverage`: Maximum leverage (default: 1.0 = no leverage)
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

## 7. Live Trading Operations

### Pre-Flight
```powershell
# Verify API connectivity
$env:PYTHONPATH='src'; python scripts/check_live_ready.py
```

### Start Live Session
```powershell
# Paper mode (safe - no real money)
$env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session --source bitunix --symbol BTCUSD --execution-mode paper --duration 10 --async --dashboard

# Live mode (REAL MONEY)
$env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session --source bitunix --symbol BTCUSD --execution-mode live --duration 60 --async --dashboard
```

### Emergency Stop
1. Press `Ctrl+C` in the terminal (triggers graceful shutdown).
2. Or create `config/KILL_SWITCH.txt` with content `TRUE`.
3. Or run: `$env:PYTHONPATH='src'; python -c "from laptop_agents.execution.bitunix_broker import BitunixBroker; ..."`

### Monitoring
- **Dashboard**: `.\scripts\live_dashboard.ps1` (http://localhost:5000)
- **Log Stream**: `Get-Content logs/system.jsonl -Wait`
- **Heartbeat**: `python scripts/monitor_heartbeat.py`

### Rate Limit Protection
When running in `--execution-mode live`, the system only sends orders to the exchange for the **final candle** in the historical batch. This prevents hitting API rate limits during the initial candle load.

### Environment Variables
Live trading requires the following in `.env`:
```env
BITUNIX_API_KEY=your_api_key
BITUNIX_API_SECRET=your_secret_key
```

## 8. Resilience & Safety (Production)

### A. Process Watchdog
To run the system with auto-restart capability (resilience):
```powershell
.\scripts\watchdog.ps1 --mode live-session --source bitunix --execution-mode live --async
```
- **Failsafe**: If the python process crashes/exits, the watchdog waits 10s and restarts it.
- **Log**: View watchdog activity in `logs/watchdog.log`.

### B. Heartbeat Monitor
Run this in a separate terminal to detect frozen processes (not just crashes):
```powershell
python scripts/monitor_heartbeat.py
```

### C. Safety Kill Switch
If you need to instantly block all new order submissions:
1. Open or create `config/KILL_SWITCH.txt`.
2. Write `TRUE` inside the file.
3. The system will log `KILL SWITCH DETECTED!` and block any further `place_order` calls.

### D. Hard-Coded Limits
The following "Hardware" limits are enforced in `src/laptop_agents/core/hard_limits.py` and cannot be overridden by CLI arguments:
- **Max Position Size**: $200,000 USD.
- **Max Daily Loss**: $50 USD.
- **Max Leverage**: 20.0x.

## 9. Monitoring & Observability

### A. Live Dashboard Server
Use the Flask-based real-time dashboard:
```powershell
.\scripts\live_dashboard.ps1
```
- **Access**: `http://localhost:5000`
- **Benefit**: Auto-refreshing equity curve, active orders, and system logs.

### B. Structured JSON Logs
The system produces machine-readable logs in `logs/system.jsonl`:
- **Format**: JSON Lines.
- **Contents**: Includes every `EVENT` logged by the system, plus error stack traces and latency metrics.

### C. Latency Tracking
Every trade fill in `live` mode now includes `latency_sec` in its event data (logged to `system.jsonl`). This measures the time from signal generation to exchange fill confirmation.

### D. Advanced Flags (Troubleshooting)
- `--async`: Use the high-performance `asyncio` + WebSockets engine (recommended for live-session).
- `--preflight`: Run connectivity and credential checks before starting.
- `--stale-timeout`: Seconds before stale WebSocket data triggers a safety shutdown (default: 60).
- `--replay <path>`: Replay a previous `events.jsonl` for deterministic debugging.

