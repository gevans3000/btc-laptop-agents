# Known Issues

> **Status**: ACTIVE

## 2026-01-11: Paper Rejected due to Notional Limits
**Issue**: Modular agents in `orchestrated` mode were generating quantities that exceeded `hard_limits.MAX_POSITION_SIZE_USD` (200k) or `MAX_LEVERAGE` (20x), causing `PaperBroker` to reject the trades.
**Impact**: Trades signals were firing but not executing in paper mode during the 8-hour stability run.
**Resolution**: Added hard limit enforcement in `Supervisor._resolve_order` to cap the quantity before it reaches the broker.
**Status**: Fixed.

## Auto-Generated Error Log

This section is automatically updated when bugs are captured via the Learning Debugger.

To view all known errors:
```powershell
python scripts/error_fingerprinter.py list
```

To search for a specific error:
```powershell
python scripts/error_fingerprinter.py lookup "<error_text>"
```

