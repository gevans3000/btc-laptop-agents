# 🚀 BTC Laptop Agents: Your Autonomous High-Frequency Trading System

> **Status**: Phase 2 Complete (Resilience & Hardening)
> **Current Capability**: 10-minute+ Autonomous Paper Trading with Real-Time Safety
> **Engine**: Python 3.11+ / Asyncio / WebSocket

## 📖 Introduction

**BTC Laptop Agents** is a privacy-first, local-running autonomous trading system designed to trade Bitcoin on the Bitunix exchange. Unlike typical command-line bots, this system is architected as an **autonomous agent** capable of self-diagnosis, self-healing, and continuous operation without human intervention.

It unifies high-frequency event processing with robust safety guardrails, allowing it to run reliably on consumer hardware ("Laptop") while mimicking institutional-grade reliability.

**Warning**: *This is a powerful financial tool. Please exercise caution with its operations, especially when authorizing real-money trading (Future Feature).*

---

## ✨ Key Features

- **⚡ The Sentinel Engine**: Processes WebSocket ticks in real-time, bypassing 1-minute candle latency for immediate Stop-Loss/Take-Profit execution.
- **🛡️ Atomic Safety**: Uses transactional file writes to ensure trading state is never corrupted, even during power loss.
- **🧠 Self-Healing Connectivity**: Circuit breakers and exponential backoff strategies prevent API bans and handle internet instability.
- **🤖 Autonomous Workflow**: Built-in agentic workflows (`/go`, `/fix`) for verifying code integrity and deploying changes safely.
- **📊 Rich Observability**: Generates visual HTML reports with trade visualization, Sharpe ratios, and real-time drawdown analysis.
- **🔬 Hybrid Simulation**: Run the exact same strategy code in high-speed Backtest mode or Real-time Paper mode.

---

## 🎬 Quick Start Guide

The entire system is controlled via the `la` (Linear Agent) CLI, designed for zero-friction operation.

### 0. Install
```powershell
pip install -e .
# Optional: dashboard support
pip install -e .[dashboard]
```

### 1. Doctor & Setup
Verify your environment, API keys, and network connectivity.
```powershell
la doctor --fix
```

### 2. Run a Live Session
Start the agent in **Live Mode** (Paper Trading) with real market data.
```powershell
# Run for 15 minutes with a live dashboard
la run --mode live-session --duration 15 --dashboard --source bitunix
```

### 3. Backtest a Strategy
Simulate performance over historical data.
```powershell
la run --mode backtest --show
```

### 4. System Status
Check the pulse of the agent, running processes, and resource usage.
```powershell
la status
```

---

## 🏗️ Architecture

```
btc-laptop-agents/
├── src/
│   ├── laptop_agents/
│   │   ├── core/           # Event Bus & Base Classes
│   │   ├── data/           # Market Data Providers (WebSocket/REST)
│   │   ├── strategies/     # Signal Generation Logic
│   │   ├── execution/      # Order Management & Sentinel Engine
│   │   ├── session/        # Session Orchestration
│   │   └── ui/             # Dashboard & Reporting
├── .agent/
│   ├── workflows/          # Autonomous Agent Capabilities (e.g., /go, /fix)
│   └── skills/             # Specialized Agent Skills (Monte Carlo, Backtest)
├── .workspace/             # Hermetic Runtime Artifacts
│   ├── runs/               # Historical Session Data
│   ├── paper/              # Live Trading State (SQLite/JSON)
│   └── logs/               # System Logs
├── config/
│   └── strategies/         # Strategy JSON Configurations
└── docs/                   # The Engineer's Bible
```

---

## 🗺️ Roadmap

### Phase 1: Foundation (✅ Completed)
- [x] **Unified CLI**: Single entry point (`la`) for all operations.
- [x] **Core Architecture**: Event-driven separation of Market Data, Strategy, and Execution.
- [x] **Paper Trading**: Basic order simulation and portfolio tracking.
- [x] **Basic Backtesting**: Historical data simulation engine.

### Phase 2: Resilience & Hardening (✅ Completed)
- [x] **Sentinel Upgrade**: Sub-second tick-based execution for precision safety.
- [x] **Reliability Overhaul**: 15+ surgical fixes for timeouts, race conditions, and error handling.
- [x] **System Status**: Comprehensive health checks (`doctor`, `status`) and environment verification.
- [x] **WebSocket Stability**: Hardened connection logic with "Zombie Connection" detection.

### Phase 3: Intelligence & Optimization (🚧 In Progress)
- [ ] **Monte Carlo Simulations**: Robustness testing to estimate failure probabilities across thousands of scenarios.
- [ ] **Hyperparameter Tuning**: Automated search for optimal strategy parameters (Sharpe/Sortino optimization).
- [ ] **Advanced Strategies**: Integration of ML-based signal generators and multi-factor models.
- [ ] **Smart Order Routing**: Splitting large orders to minimize slippage (TWAP/VWAP).

### Phase 4: Moonshots (🔮 Future)
- [ ] **Real Money Execution**: Graduated rollout from Paper to Live trading with hard capital limits.
- [ ] **Multi-Strategy Portfolio**: Running uncorrelated strategies simultaneously to smooth returns.
- [ ] **Distributed Deployment**: Moving from Laptop to Cloud/VPS for 24/7 uptime guarantees.
- [ ] **Sentiment Analysis**: Ingesting news/social data to effectively hedge against "Black Swan" events.
- [ ] **LLM Strategy Design**: Agent-driven strategy creation and self-improvement loops.

---

## �️ Contributing

We welcome contributions! Whether it's a new Strategy, a UI fix, or a security improvement:
1. Fork the repo.
2. Create a branch (`git checkout -b feat/NewStrategy`).
3. Submit a PR.

---

## � License
MIT © BTC Laptop Agents Team
