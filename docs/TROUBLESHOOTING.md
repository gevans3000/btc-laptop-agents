# Troubleshooting Guide

## Automated Diagnostics (`la doctor`)
The fastest way to fix issues is to run the automated doctor:
```bash
la doctor --fix
```
This tool checks:
- Python version compatibility.
- `.env` file presence and key validation.
- Directory permissions for `.workspace/`.
- Internet connectivity to Bitunix.

## Common Issues

### 1. "Circuit Breaker Open"
**Symptom**: Agent logs `CircuitBreakerOpen` and skips processing.
**Cause**: The agent has hit the max consecutive loss limit (5 trades) or max daily drawdown.
**Fix**:
1. Review the logs in `.workspace/logs/system.log`.
2. If safe, restart the session to reset the in-memory breaker (Daily limits persist in `daily_checkpoint.json`).

### 2. "LowCandleCountWarning"
**Symptom**: Session starts but warns about `< 51 candles`.
**Cause**: The agent has hit a cold start where it hasn't fetched enough history to compute the EMA(50) for trend filtering.
**Fix**: Ensure your internet connection is stable so `BitunixFuturesProvider` can fetch the initial history snapshot.

### 3. "Zombie Connection"
**Symptom**: Logs show `WS: Connection became zombie`.
**Cause**: The WebSocket stopped receiving data but didn't disconnect.
**Fix**: The system automatically detects this after 60s and reconnects. No user action valid.

### 4. Config Validation Errors
**Symptom**: `CONFIG VALIDATION ERROR` on startup.
**Cause**: `config/strategies/*.json` contains values that exceed `constants.py` hard limits.
**Fix**: Adjust your strategy configuration to be strictly *tighter* than the system hard limits.
