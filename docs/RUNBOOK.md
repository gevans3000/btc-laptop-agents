# RUNBOOK.md — Operations Manual

> **Status**: ACTIVE

> **Scope**: The authoritative guide for operating the BTC Laptop Agents MVP.
> **Audience**: Humans and Agents.

## 1. Quick Reference

| Action | Script | Expected Output |
| :--- | :--- | :--- |
| **Verify System** | `.\scripts\verify.ps1` | `VERIFY: PASS` |
| **Start (Agents)** | `.\scripts\watchdog.ps1` | Monitors and restarts trading daemon. |
| **View Dashboard** | `.\scripts\dashboard_up.ps1` | Interactive UI on `http://localhost:8000` |
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
Before running any live code, ALWAYS run the verification suite:
```powershell
.\scripts\verify.ps1
```
This checks compilation, runs deterministic risk engine tests, and validates artifact schemas.

## 3. Operational Modes

The system primarily runs through `src/laptop_agents/run.py`.

### A. Orchestrated Mode (Multi-Agent)
This is the modern pipeline using the modular agent stack (Market Intake -> Analysis -> Execution).
- **Run Once (Simulation)**: 
  `python -m src.laptop_agents.run --mode orchestrated --source mock`
- **Live Trading**: 
  `python -m src.laptop_agents.run --mode orchestrated --source bitunix --execution-mode live`

### B. Production Deployment (Recommended)
Use the **Watchdog** for live trading to ensure the bot survives crashes or internet blips:
```powershell
.\scripts\watchdog.ps1 --mode orchestrated --source bitunix --execution-mode live
```
- Logs are located in `logs/watchdog.log`.
- Trading state events are in `logs/system.jsonl`.

### C. Checking Status & Recovery
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
$env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session --source bitunix --symbol BTCUSD --execution-mode paper --duration 10

# Live mode (REAL MONEY)
$env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session --source bitunix --symbol BTCUSD --execution-mode live --duration 10
```

### Emergency Stop
1. Press `Ctrl+C` in the terminal (triggers graceful shutdown).
2. Or create `config/KILL_SWITCH.txt` with content `TRUE`.
3. Or run: `$env:PYTHONPATH='src'; python -c "from laptop_agents.execution.bitunix_broker import BitunixBroker; ..."`

### Monitoring
- Heartbeat: `logs/heartbeat.json`
- Events: `paper/events.jsonl`
- Equity checkpoint: `logs/daily_checkpoint.json`

### C. Rate Limit Protection
When running in `--execution-mode live`, the system only sends orders to the exchange for the **final candle** in the historical batch. This prevents hitting API rate limits during the initial candle load.

### D. Environment Variables
Live trading requires the following in `.env`:
```env
BITUNIX_API_KEY=your_api_key
BITUNIX_API_SECRET=your_secret_key
```

### E. Watchdog Parameters
The watchdog now supports all CLI parameters:
```powershell
.\scripts\watchdog.ps1 -Mode orchestrated -Source bitunix -Symbol BTCUSD -Interval 1m -Limit 480 -ExecutionMode live -RiskPct 0.5
```

## 8. Resilience & Safety (Production)

### A. Process Watchdog
To run the system with auto-restart capability (resilience):
```powershell
.\scripts\watchdog.ps1 --mode orchestrated --source bitunix --limit 200 --execution-mode live
```
- **Failsafe**: If the python process crashes/exits, the watchdog waits 10s and restarts it.
- **Log**: View watchdog activity in `logs/watchdog.log`.

### B. Safety Kill Switch
If you need to instantly block all new order submissions:
1. Open or create `config/KILL_SWITCH.txt`.
2. Write `TRUE` inside the file.
3. The system will log `KILL SWITCH DETECTED!` and block any further `place_order` calls.

### C. Hard-Coded Limits
The following "Hardware" limits are enforced in `src/laptop_agents/core/hard_limits.py` and cannot be overridden by CLI arguments:
- **Max Position Size**: $200,000 USD.
- **Max Daily Loss**: $50 USD.
- **Max Leverage**: 20.0x.

## 9. Monitoring & Observability

### A. Live Dashboard Server
Instead of opening a static file, serve the results locally:
```powershell
.\scripts\dashboard_up.ps1
```
- **Access**: `http://localhost:8000/summary.html`
- **Benefit**: Keeps the dashboard accessible and allows for automated refreshes (future).

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

