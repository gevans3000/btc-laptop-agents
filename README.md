# 🚀 BTC Laptop Agents: Autonomous Trading System

> **Status**: Active & Hardened
> **Capability**: 10-minute+ Autonomous Sessions (Paper/Live)
> **Engine**: Python 3.12+ / Asyncio / Typer / WebSocket

**BTC Laptop Agents** is a privacy-first, local-first autonomous trading system. Unlike distinct "bots", it runs as a continuous agentic loop that owns the entire lifecycle—from data ingestion to safety checks and execution—guarded by non-negotiable hard limits.

## ⚡ Quick Start

### 1. Install & Verify
```powershell
# Standard install (use .[test] for dev-dependencies)
pip install -e .
la doctor --fix
```

### 2. Paper Trading (Live Data)
Run a safe, 15-minute autonomous session against real Bitunix market data (no real money used):
```powershell
la run --mode live-session --duration 15 --source bitunix
```

### 3. Backtest
Simulate strategy performance on historical data:
```powershell
la backtest --days 5 --symbol BTCUSDT
```

### 4. System Status
Check the agent's heartbeat and active processes:
```powershell
la status
```

## 📚 Documentation
- **[ENGINEER.md](docs/ENGINEER.md)**: **The Single Source of Truth**. Read this for operational commands, architecture, and configuration.
- **[CONTRIBUTING.md](docs/CONTRIBUTING.md)**: Development guide, testing strategies, and review protocols.
- **[PROTOCOL](docs/AI_ENGINEERING_PROTOCOL.md)**: Rules for AI agents modification of this codebase.

## ⚙️ Configuration
See **[ENGINEER.md](docs/ENGINEER.md#3-configuration-formats--precedence)** for full configuration precedence and formats.
- **Session config**: JSON files via `--config`.
- **Strategy config**: JSON files in `config/strategies/`.
- **Risk/Exchange**: YAML files in `config/`.

## 🛡️ Safety & Architecture
- **Hard Limits**: `constants.py` loads risk ceilings from `config/defaults.yaml` (with code fallbacks), so changes require a repo/config update (e.g., Max $50 loss/day).
- **Hermetic Workspace**: All logs, state, and artifacts live in `.workspace/`.
- **Resilience**: Integrated "Circuit Breakers" and "Zombie Connection" detection.

## ⚙️ Reproducibility (CI)
This repository uses a `requirements.lock` file to ensure strictly reproducible builds in CI and production.
- To update dependencies: Modify `pyproject.toml` and run `pip-compile`.
- To install exactly as CI: `pip install -r requirements.lock`.

## 🛡️ Architecture
- **Async Outer Shell**: The `AsyncRunner` handles high-concurrency tasks like WebSocket ingestion, heartbeats, and watchdog monitoring.
- **Sync Domain Logic**: Agent decision-making (Supervisor) is strictly synchronous. This guarantees deterministic behavior and prevents race conditions within the trading strategy, making it optimized for "laptop-scale" performance.

## 🤝 Contributing
See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for workflows.
