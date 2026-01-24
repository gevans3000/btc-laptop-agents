# 10-Minute Paper Trading Test Plan

## Overview
This document outlines the test plan for evaluating the autonomy and safety of the trading app during a 10-minute paper trading session.

---

## Pre-Run Setup Steps

### 1. Configuration
- Ensure the strategy configuration file (e.g., [`config/strategies/scalp_1m_sweep.json`](config/strategies/scalp_1m_sweep.json)) is correctly loaded.
- Verify that the `execution_mode` is set to `paper` in the session configuration.
- Confirm that the `symbol`, `interval`, and `source` are appropriately set (e.g., `BTCUSDT`, `1m`, `mock`).

### 2. Environment
- Ensure the `.workspace` directory exists for storing logs and artifacts.
- Validate that the logging system is initialized and configured to capture events in both JSON and console formats.

### 3. Risk Parameters
- Confirm that risk parameters (e.g., `risk_pct`, `stop_bps`, `tp_r`) are set within acceptable limits.
- Ensure hard limits (e.g., `MAX_POSITION_SIZE_USD`, `MAX_DAILY_LOSS_USD`) are enforced.

### 4. Data Source
- If using a mock data provider, ensure it is generating realistic candle data for the specified interval.
- If using a live data provider (e.g., Bitunix), verify that the WebSocket connection is stable.

---

## Success Criteria

At the end of the 10-minute run, the following must be true:

### 1. Autonomy
- The app must execute the strategy loop (signal → decision → order → monitoring → exit) without manual intervention.
- No crashes or unhandled exceptions should occur.

### 2. Order Lifecycle
- All orders must transition through the expected states (submitted, filled, canceled, or rejected).
- Positions must be opened and closed based on the strategy's signals.

### 3. Risk Management
- No position should exceed the predefined risk limits (e.g., `MAX_POSITION_SIZE_USD`).
- Stop-loss and take-profit levels must be respected.

### 4. Logging and Telemetry
- All events (e.g., `PositionOpened`, `PositionClosed`, `RiskSizingSkipped`) must be logged with timestamps.
- Logs must be written to both the console and JSON file for audit purposes.

### 5. State Management
- The app must save and restore its state correctly (e.g., [`paper/state.json`](paper/state.json)).
- The final state must reflect accurate equity, PnL, and position data.

---

## Failure Criteria

The test fails if any of the following occur:

### 1. Crashes or Errors
- The app crashes or encounters an unhandled exception.
- The circuit breaker opens due to repeated failures.

### 2. Data Issues
- The market data stream drops or becomes unstable.
- Candles are missing or incorrectly processed.

### 3. Order Execution Issues
- Orders are not executed as expected (e.g., stuck in `submitted` state).
- Positions are not closed when stop-loss or take-profit levels are hit.

### 4. Risk Violations
- Positions exceed predefined risk limits.
- The daily loss limit is breached without triggering a shutdown.

### 5. Logging Gaps
- Critical events (e.g., order execution, errors) are not logged.
- Logs are incomplete or missing required fields (e.g., timestamps, event types).

---

## Test Cases

| Test Case | Description | Expected Outcome |
|-----------|-------------|------------------|
| **Normal Execution** | Run the strategy for 10 minutes with realistic candle data. | Orders are executed, positions are managed, and PnL is calculated correctly. |
| **Edge Case: Stop-Loss Hit** | Simulate a candle that triggers a stop-loss. | Position is closed at the stop price, and the event is logged. |
| **Edge Case: Take-Profit Hit** | Simulate a candle that triggers a take-profit. | Position is closed at the take-profit price, and the event is logged. |
| **Edge Case: Data Drop** | Simulate a temporary loss of market data. | The app recovers gracefully and continues execution. |
| **Edge Case: Circuit Breaker** | Simulate repeated failures to trigger the circuit breaker. | The circuit breaker opens, and no further orders are executed. |

---

## Metrics to Capture

1. **Latency**:
   - Time taken to process each candle and execute orders.
2. **Dropped Ticks**:
   - Number of candles missed or delayed.
3. **Order Response Time**:
   - Time between signal generation and order execution.
4. **PnL Calculation Integrity**:
   - Verify that PnL calculations are accurate and consistent.
5. **Error Rates**:
   - Number of errors encountered and their resolution status.

---

## Evidence to Collect

1. **Logs**:
   - JSON logs from `.workspace/logs/system.jsonl`.
   - Console logs capturing all events.
2. **State Files**:
   - [`paper/state.json`](paper/state.json) for final equity and position data.
3. **Trade Reports**:
   - [`paper/trades.csv`](paper/trades.csv) for executed trades.
4. **Event Logs**:
   - [`paper/events.jsonl`](paper/events.jsonl) for all strategy events.
5. **Screenshots**:
   - If applicable, capture UI states or dashboard outputs.

---

## Conversion-to-Live Readiness Assessment

To safely convert to live trading, the following must be addressed:

1. **Credentials Management**:
   - Ensure API keys and secrets are securely stored and not hardcoded.
2. **Slippage and Fees Model**:
   - Adjust slippage and fee calculations to match live market conditions.
3. **Order Sizing and Compliance**:
   - Ensure order sizes comply with exchange-specific constraints.
4. **Kill Switch**:
   - Implement a kill switch to halt trading in case of emergencies.
5. **Monitoring and Alerting**:
   - Set up email/Slack alerts for critical events (e.g., circuit breaker trips).
6. **Broker/Exchange API Differences**:
   - Test compatibility with live exchange APIs (e.g., Bitunix).
7. **Environment Separation**:
   - Ensure paper and live environments are isolated to prevent accidental live orders.

---

## Deliverables Format

1. **Pass/Fail Rubric**:
   - A checklist to evaluate the app's autonomy and safety.
2. **Prioritized Gaps**:
   - Critical: Issues that must be fixed before live trading.
   - High: Issues that could impact performance or safety.
   - Medium: Issues that should be addressed but are not critical.
   - Low: Minor issues or improvements.
3. **Recommendations**:
   - Example log schemas and state diagrams for clarity.

---

## Next Steps

Proceed with executing the test plan and collecting the required evidence. Once completed, review the results and prioritize any gaps for live trading conversion.
