---
description: Autonomous documentation cleanup and alignment for btc-laptop-agents
---

# Documentation Cleanup Workflow

**Goal**: Align all Markdown documentation with the current Live Trading System architecture. Execute each phase sequentially, committing after each phase.

---

## Pre-Flight Checklist

// turbo
1. Verify you are on a clean branch:
```powershell
git status
```

// turbo
2. Create a new branch for this work:
```powershell
git checkout -b docs/cleanup-alignment
```

---

## PHASE 1: Delete Deprecated Files

These files are explicitly deprecated and should be removed.

// turbo
1.1. Delete `MVP_COMMANDS_README.md` (moved to `docs/RUNBOOK.md`):
```powershell
Remove-Item -Force "MVP_COMMANDS_README.md"
```

// turbo
1.2. Delete `docs/MVP_SPEC.md` (superseded by `docs/SPEC.md`):
```powershell
Remove-Item -Force "docs/MVP_SPEC.md"
```

// turbo
1.3. Delete `docs/MVP_TARGET.md` (superseded by `docs/SPEC.md`):
```powershell
Remove-Item -Force "docs/MVP_TARGET.md"
```

// turbo
1.4. Commit Phase 1:
```powershell
git add -A; git commit -m "docs: remove deprecated MVP_SPEC, MVP_TARGET, MVP_COMMANDS_README"
```

---

## PHASE 2: Update Core Documentation Files

### 2.1. Update `docs/MAP.md`

Open `docs/MAP.md` and ensure the following entries are present and accurate:

| Logic Area | Location | Primary Function(s) |
| :--- | :--- | :--- |
| **CLI Entry** | `src/laptop_agents/run.py` | Command-line interface wrapper. |
| **Orchestrator** | `src/laptop_agents/core/orchestrator.py` | Main coordination logic (`run_orchestrated_mode`). |
| **Data Loader** | `src/laptop_agents/data/loader.py` | Candle fetching. |
| **Timed Session** | `src/laptop_agents/session/timed_session.py` | Autonomous polling loop for live sessions. |
| **Live Broker** | `src/laptop_agents/execution/bitunix_broker.py` | Real-money execution with Bitunix. |
| **Bitunix Provider** | `src/laptop_agents/data/providers/bitunix_futures.py` | API client for Bitunix Futures. |
| **Paper Broker** | `src/laptop_agents/paper/broker.py` | Simulated execution for backtesting. |
| **Backtest Engine** | `src/laptop_agents/backtest/engine.py` | Historical simulation. |
| **Modular Agents** | `src/laptop_agents/agents/` | Strategy signals and state management. |
| **Resilience** | `src/laptop_agents/resilience/` | Circuit breakers, retries, error handling. |
| **Hard Limits** | `src/laptop_agents/core/hard_limits.py` | Immutable safety constraints. |

**Add a new section "4. Live Trading System":**

```markdown
## 4. Live Trading System

| Component | Location | Purpose |
| :--- | :--- | :--- |
| **Readiness Check** | `scripts/check_live_ready.py` | Verify API credentials and connectivity. |
| **Live Session** | `--mode live-session --execution-mode live` | Run autonomous trading session. |
| **Kill Switch** | `config/KILL_SWITCH.txt` | Set content to `TRUE` to halt all trading. |
| **Shutdown** | `BitunixBroker.shutdown()` | Emergency cancel all orders + close positions. |
```

### 2.2. Update `docs/SPEC.md`

Open `docs/SPEC.md` and add/update the following:

**In Section 2 (Interface Prompts & Modes), add to Primary Modes table:**

```markdown
| **Live Session** | `--mode live-session` | Autonomous polling loop for timed trading. | `paper/events.jsonl` |
```

**Add a new Section 7: Live Trading**

```markdown
## 7. Live Trading

### Execution Modes
| Mode | Flag | Description |
| :--- | :--- | :--- |
| **Paper** | `--execution-mode paper` | Simulated fills using PaperBroker. |
| **Live** | `--execution-mode live` | Real orders via BitunixBroker. |

### Safety Features
1. **Fixed $10 Sizing**: All live orders are forced to $10 notional value.
2. **Human Confirmation**: Orders require manual `y` confirmation unless `SKIP_LIVE_CONFIRM=TRUE`.
3. **Kill Switch**: Create `config/KILL_SWITCH.txt` with `TRUE` to halt all orders.
4. **Graceful Shutdown**: Ctrl+C triggers `shutdown()` which cancels orders and closes positions.

### Quick Start
```powershell
# 1. Verify readiness
$env:PYTHONPATH='src'; python scripts/check_live_ready.py

# 2. Run 10-minute paper session with live data
$env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session --source bitunix --symbol BTCUSD --execution-mode paper --duration 10

# 3. Run live session (REAL MONEY - requires confirmation)
$env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session --source bitunix --symbol BTCUSD --execution-mode live --duration 10
```
```

### 2.3. Update `docs/API_REFERENCE.md`

Open `docs/API_REFERENCE.md` and ensure these classes are documented:

```markdown
## Brokers

### `laptop_agents.paper.broker.PaperBroker`
Simulated broker for backtesting and paper trading.
- `on_candle(candle, order)` → Process candle, return fill/exit events.
- `get_unrealized_pnl(price)` → Calculate unrealized P&L.

### `laptop_agents.execution.bitunix_broker.BitunixBroker`
Real-money broker for Bitunix Futures.
- `on_candle(candle, order)` → Submit orders, poll positions, detect drift.
- `shutdown()` → Emergency cancel all orders + close all positions.
- `get_unrealized_pnl(price)` → Calculate unrealized P&L.

## Providers

### `laptop_agents.data.providers.bitunix_futures.BitunixFuturesProvider`
API client for Bitunix Futures exchange.
- `get_pending_positions(symbol)` → Fetch open positions.
- `get_open_orders(symbol)` → Fetch unfilled orders.
- `place_order(side, qty, ...)` → Submit order.
- `cancel_order(order_id, symbol)` → Cancel specific order.
- `cancel_all_orders(symbol)` → Cancel all orders for symbol.
- `klines(interval, limit)` → Fetch candle data.
```

// turbo
2.4. Commit Phase 2:
```powershell
git add -A; git commit -m "docs: update MAP, SPEC, API_REFERENCE for live trading system"
```

---

## PHASE 3: Update Supporting Documentation

### 3.1. Update `docs/RUNBOOK.md`

Add a new section for Live Trading operations:

```markdown
## Live Trading Operations

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
```

### 3.2. Update `docs/TESTING.md`

Add test commands for the live system:

```markdown
## Live Trading System Tests

### Unit Tests
```powershell
$env:PYTHONPATH='src'; python scripts/test_live_system.py
```

### Integration Test (Paper Mode)
```powershell
$env:PYTHONPATH='src'; python src/laptop_agents/run.py --mode live-session --source bitunix --symbol BTCUSD --execution-mode paper --duration 2
```
```

### 3.3. Update `docs/AI_HANDOFF.md`

Ensure this file accurately describes the current architecture:

```markdown
# AI Handoff Document

## Architecture Summary
- **CLI**: `src/laptop_agents/run.py` - Thin wrapper, delegates to orchestrator.
- **Orchestrator**: `src/laptop_agents/core/orchestrator.py` - Coordinates all modes.
- **Timed Session**: `src/laptop_agents/session/timed_session.py` - Live polling loop.
- **Brokers**: `PaperBroker` (simulation), `BitunixBroker` (live).

## Key Concepts
1. **Execution Mode**: `paper` vs `live` determines broker selection.
2. **Data Source**: `mock` vs `bitunix` determines candle source.
3. **Safety**: Hard limits in `core/hard_limits.py` are immutable.

## Recent Changes
- Added Live Trading System (BitunixBroker with $10 fixed sizing).
- Added `cancel_order`, `cancel_all_orders` to BitunixFuturesProvider.
- Added `shutdown()` method for graceful cleanup.
- Added `execution_mode` parameter to timed_session.
```

// turbo
3.4. Commit Phase 3:
```powershell
git add -A; git commit -m "docs: update RUNBOOK, TESTING, AI_HANDOFF for live trading"
```

---

## PHASE 4: Cleanup Stale References

### 4.1. Search for outdated references

// turbo
Search for any remaining references to deprecated files:
```powershell
Select-String -Path "docs/*.md" -Pattern "MVP_SPEC|MVP_TARGET|MVP_COMMANDS" -SimpleMatch
```

If any matches are found, update those files to remove or replace the references.

### 4.2. Search for monolith references

// turbo
Search for references to the old monolith architecture:
```powershell
Select-String -Path "docs/*.md" -Pattern "monolith|monolithic" -SimpleMatch
```

Update any found references to clarify that the system is now modular.

// turbo
4.3. Commit Phase 4:
```powershell
git add -A; git commit -m "docs: remove stale references to deprecated files"
```

---

## PHASE 5: Final Verification

// turbo
5.1. Verify all documentation files exist and are valid:
```powershell
Get-ChildItem docs/*.md | ForEach-Object { Write-Host "OK: $($_.Name)" }
```

// turbo
5.2. Run the live system test to ensure nothing broke:
```powershell
$env:PYTHONPATH='src'; python scripts/test_live_system.py
```

// turbo
5.3. Push the branch:
```powershell
git push -u origin docs/cleanup-alignment
```

---

## Completion Checklist

After executing all phases, verify:
- [ ] `MVP_SPEC.md`, `MVP_TARGET.md`, `MVP_COMMANDS_README.md` are deleted
- [ ] `docs/MAP.md` includes Live Trading System section
- [ ] `docs/SPEC.md` includes Section 7: Live Trading
- [ ] `docs/API_REFERENCE.md` documents BitunixBroker and BitunixFuturesProvider
- [ ] `docs/RUNBOOK.md` has Live Trading Operations section
- [ ] `docs/TESTING.md` has Live Trading System Tests section
- [ ] `docs/AI_HANDOFF.md` reflects current modular architecture
- [ ] No remaining references to deprecated MVP files
- [ ] All tests pass
