# 🚀 BTC Laptop Agents: Autonomous Trading System

> **Status**: Active & Hardened
> **Capability**: 10-minute+ Autonomous Sessions (Paper/Live)
> **Engine**: Python 3.11+ / Asyncio / Typer / WebSocket

**BTC Laptop Agents** is a privacy-first, local-first autonomous trading system. Unlike distinct "bots", it runs as a continuous agentic loop that owns the entire lifecycle—from data ingestion to safety checks and execution—guarded by non-negotiable hard limits.

## ⚡ Quick Start

### 1. Install & Verify
```powershell
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

## ⚙️ Configuration Formats
- **Session config**: JSON file passed via `--config` (see `SessionConfig` in `src/laptop_agents/core/config.py`).
- **Strategy config**: JSON files in `config/strategies/<name>.json` loaded via `--strategy`.
- **Risk/exchange config**: YAML files in `config/risk.yaml` and `config/exchanges/bitunix.yaml`.

## 🛡️ Safety & Architecture
- **Hard Limits**: `constants.py` defines immutable risk ceilings (e.g., Max $50 loss/day).
- **Hermetic Workspace**: All logs, state, and artifacts live in `.workspace/`.
- **Resilience**: Integrated "Circuit Breakers" and "Zombie Connection" detection.

## 🤝 Contributing
See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for workflows.
