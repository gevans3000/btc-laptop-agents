# MVP Contract for BTC Laptop Agents

This document defines the minimum viable product (MVP) contract for the BTC Laptop Agents project. It outlines the required outputs, schemas, and validation criteria for a successful v1 release.

## Required Outputs

The following artifacts must be generated and validated for each run:

### 1. `runs/latest/events.jsonl`
- **Format**: JSON Lines (append-only)
- **Purpose**: Log all events during the run, including stage boundaries, errors, and decisions.
- **Schema**:
  ```json
  {
    "timestamp": "ISO8601",
    "event": "string",
    "run_id": "string",
    "stage": "string (optional)",
    "ok": "boolean (optional)",
    "error": "string (optional)",
    "artifact_paths": "list of strings (optional)"
  }
  ```

### 2. `runs/latest/trades.csv`
- **Format**: CSV (append-only)
- **Purpose**: Record all trades executed during the run.
- **Schema**:
  ```csv
  trade_id,side,signal,entry,exit,price,quantity,pnl,fees,entry_ts,exit_ts,timestamp,exit_reason,stop_price,tp_price
  ```

### 3. `runs/latest/summary.html`
- **Format**: HTML (overwrite)
- **Purpose**: Provide a human-readable summary of the run, including key metrics, trades, and visualizations.
- **Content**:
  - Run metadata (run_id, mode, source, symbol, interval)
  - Key metrics (net PnL, win rate, max drawdown, fees)
  - Equity curve visualization
  - Last 10 trades
  - Events tail

## Event Fields

The following fields must be included in all events logged to `events.jsonl`:

- `run_id`: Unique identifier for the run
- `stage`: Current stage of the pipeline (e.g., "data_loading", "signal_generation", "execution")
- `ok`: Boolean indicating success or failure of the stage
- `error`: Error message (if applicable)
- `artifact_paths`: List of paths to artifacts generated during the stage
- `timestamp`: ISO8601 timestamp of the event

## Validation Criteria

### Candle Integrity Gate
- **Purpose**: Ensure that candle data is valid and consistent.
- **Checks**:
  - Candles are in chronological order
  - No missing or duplicate timestamps
  - Valid OHLCV values (open, high, low, close, volume)

### Feature Sanity Gate
- **Purpose**: Validate that computed features are within expected ranges.
- **Checks**:
  - SMA values are within reasonable bounds
  - No NaN or infinite values in features
  - Feature consistency across timeframes

### Trade Idea Schema Gate
- **Purpose**: Ensure that trade ideas adhere to the defined schema.
- **Checks**:
  - Required fields are present (signal, entry, stop, tp)
  - Valid signal values (BUY, SELL)
  - Stop and TP prices are correctly ordered (stop < entry < tp for LONG, tp < entry < stop for SHORT)

### Risk Invariant Gate
- **Purpose**: Enforce risk management rules.
- **Checks**:
  - Maximum risk per trade (e.g., 1% of equity)
  - Minimum reward-to-risk ratio (e.g., 1.5)
  - Daily stop loss limit (e.g., 5% of equity)

### Execution Determinism Gate
- **Purpose**: Ensure that the same inputs produce the same outputs.
- **Checks**:
  - Replayability of runs from artifacts
  - Consistency of trade outcomes given the same inputs

## Artifacts Structure

All artifacts for a run must be stored under `runs/<run_id>/artifacts/`:

- `candles.json`: Raw candle data used for the run
- `features.json`: Computed features (e.g., SMAs, indicators)
- `decision.json`: Trade decisions and signals
- `risk.json`: Risk management calculations
- `fills.json`: Execution details and fills

## Replayability

The `scripts/replay_run.ps1` script must be able to replay a run from its artifacts:

```powershell
./scripts/replay_run.ps1 --run_id <run_id>
```

This script should:
1. Load artifacts from `runs/<run_id>/artifacts/`
2. Reconstruct the run state
3. Recompute outputs
4. Validate consistency with the original run

## Control Surface

The control surface must provide the following operations:

- **Start**: Launch the orchestrated loop and write a PID file
- **Stop**: Stop the loop using a stopfile or PID kill
- **Status**: Read the last event and run_id
- **Open**: Open `runs/latest/summary.html` in the default browser

## Reliability

The watchdog script must support:

- Restart on crash
- Maximum restart attempts (e.g., 5)
- Exponential backoff between restart attempts
- Clear "last known good run" pointer

## Future Enhancements

The following features are out of scope for v1 but should be considered for future releases:

- Multi-timeframe support
- Market microstructure realism (slippage, fees, spread simulation)
- Strategy versioning and explainability
- Expanded risk engine (position sizing by ATR, portfolio constraints)
- Deterministic backtest mode
- Metrics and scoring (win rate, drawdown, expectancy)
- Regression evaluations
- Unified HTML dashboard
- Export and audit capabilities
- Parallel workers and task graph dispatcher
- Config system and observability
- Packaging and installer
