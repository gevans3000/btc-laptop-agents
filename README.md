# BTC Laptop Agents - Unified Trading System

> **Status**: Phase 3 Complete (Structural Polish)
> **Version**: 1.1.0

BTC Laptop Agents is a local-first, privacy-focused paper trading system for Bitcoin. It has been unified into a single Python-based CLI (`la`) for maximum reliability and minimum cognitive load.

---

## 🚀 Quick Start (Unified CLI)

The whole system is now operated via the `la` command.

```powershell
# 1. Setup & Verify Environment
la doctor --fix

# 2. Run a 10-minute Paper Session (Async + WebSockets)
la run --mode live-session --duration 10 --dashboard

# 3. Check System Status
la status

# 4. Stop Session
la stop
```

---

## 🛠️ Unified CLI Reference

| Command | Description |
| :--- | :--- |
| `la run` | Start a trading session (Backtest, Live-Session, etc.) |
| `la start` | Start a session in the background (detached) |
| `la stop` | Stop any running session |
| `la watch` | Monitor and auto-restart a session on crash |
| `la status` | Check system vitals and running process |
| `la doctor` | Diagnostic tool to verify environment and API |
| `la clean` | Clean up old run artifacts |

### Common Flags for `la run`
- `--mode`: `backtest`, `live-session`, `orchestrated`
- `--source`: `mock`, `bitunix`
- `--symbol`: `BTCUSDT` (default)
- `--duration`: Minutes for live-session
- `--async`: Use high-performance execution engine
- `--dashboard`: Launch real-time web dashboard
- `--show`: Auto-open `summary.html` after run

---

## 📖 Complete Documentation

All operational and technical details are now consolidated in a single "Engineer's Bible":

👉 **[docs/ENGINEER.md](docs/ENGINEER.md)**

---

## 🔍 How to Confirm EVERYTHING is OFF

```powershell
# 1. Use unified status
la status
# Should show: STOPPED

# 2. Stop anyway (safety)
la stop

# 3. Check for lingering PID
Test-Path .workspace/agent.pid
# Should return False
```

---

## 📂 Hermetic Workspace

All system artifacts are stored in `.workspace/` to keep the root clean:

| Path | Purpose |
|------|---------|
| `.workspace/runs/` | Historical run data |
| `.workspace/runs/latest/` | Current/most recent run |
| `.workspace/logs/` | System and supervisor logs |
| `.workspace/paper/` | Paper trading state |
| `.workspace/agent.pid` | Process management |
| `config/strategies/` | Strategy configurations |
| `config/KILL_SWITCH.txt` | Emergency stop (set to TRUE to halt) |

---

## ⚖️ Safety & Resilience

- **Supervisor**: `la watch` ensures your trading session restarts within 10s of a crash.
- **Hard Limits**: Enforced $50 max daily loss and $200k max position size.
- **Kill Switch**: Create `config/KILL_SWITCH.txt` with `TRUE` to halt all trading instantly.
