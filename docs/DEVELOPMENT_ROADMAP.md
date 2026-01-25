# BTC Laptop Agents — Production Roadmap

> **Author**: AI Senior Engineer / Quant PM Review
> **Date**: January 2025
> **Goal**: Transform this repo into a production-grade Bitcoin trading system with backtest↔live parity

---

## 1. Repo Assessment (Current State)

### 1.1 What the Repo Does Today

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CURRENT ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   CLI (Typer)                                                                │
│       │                                                                      │
│       ▼                                                                      │
│   ┌──────────────────┐     ┌─────────────────┐                               │
│   │  AsyncRunner     │────▶│ BitunixProvider │ (REST + WebSocket)            │
│   │  (session loop)  │     │ or ReplayProvider│                              │
│   └────────┬─────────┘     └─────────────────┘                               │
│            │                                                                 │
│            ▼                                                                 │
│   ┌──────────────────────────────────────────────────────────────┐           │
│   │                      Supervisor.step(state, candle)           │           │
│   │  ┌─────────┐ ┌──────────────┐ ┌─────────────┐ ┌────────────┐ │           │
│   │  │ Market  │→│ Derivatives  │→│ CVD/Setup   │→│ ExecRisk   │ │           │
│   │  │ Intake  │ │ Flows        │ │ Signals     │ │ Sentinel   │ │           │
│   │  └─────────┘ └──────────────┘ └─────────────┘ └────────────┘ │           │
│   │                                        │                      │           │
│   │                              ┌─────────▼─────────┐            │           │
│   │                              │    RiskGate       │            │           │
│   │                              └─────────┬─────────┘            │           │
│   └────────────────────────────────────────┼─────────────────────┘           │
│                                            │                                 │
│                                            ▼                                 │
│   ┌───────────────────────────────────────────────────────────────┐          │
│   │  Broker (PaperBroker / BitunixBroker)                         │          │
│   │  • on_candle() → fills, exits                                 │          │
│   │  • Position tracking, SL/TP, trailing stops                   │          │
│   │  • SQLite state persistence (.workspace/paper/broker_state.db)│          │
│   └───────────────────────────────────────────────────────────────┘          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Modules:**
| Module | Location | Purpose |
|--------|----------|---------|
| CLI | `main.py`, `cli.py` | Typer-based `la` commands |
| Agents | `agents/supervisor.py` | Linear pipeline: intake→derivatives→signals→risk→journal |
| Paper Broker | `paper/broker.py` | Simulated execution with fees, slippage, SL/TP, trailing stops |
| Live Broker | `execution/bitunix_broker.py` | REST order submission + position polling |
| Data Providers | `data/providers/bitunix_futures.py` | REST history + WebSocket real-time |
| Backtest Engine | `backtest/engine.py` | Vectorized single-bar simulation (separate from agent pipeline) |
| Session Mgmt | `session/async_session.py` | AsyncRunner loop, watchdog, heartbeat |
| Constants | `constants.py` | Hard limits loaded from `config/defaults.yaml` |

**Strengths:**
- Clean `BrokerProtocol` interface for paper/live swap
- Good safety guards: circuit breaker, kill switch, max loss, max leverage
- SQLite WAL for position persistence
- Modular agent pipeline with deterministic step()
- Replay provider for recorded data playback

### 1.2 Gaps vs Target Product

| Gap Category | Current State | Required State | Risk |
|--------------|---------------|----------------|------|
| **Backtest Engine** | Separate vectorized code in `backtest/engine.py` with different logic than live pipeline | Same Supervisor + Broker path for backtest, paper, live | HIGH — PnL divergence |
| **Fill Modeling** | Basic slippage (bps), no partial fills, no queue position | Configurable slippage models, partial fills, latency injection | MEDIUM |
| **Order Book / Spread** | Not modeled; uses mid-price or close | Bid/Ask spread modeling for realistic entry/exit | MEDIUM |
| **Funding Rates** | `apply_funding()` exists but not integrated in backtest | Historical funding rates applied during backtest | LOW |
| **Strategy Interface** | Mixed: `BaseStrategy` class + agent-based setups | Unified strategy interface that works across all modes | MEDIUM |
| **Config Profiles** | Scattered: CLI flags, env vars, YAML, JSON | Single "profile" system: `backtest`, `paper`, `live` | MEDIUM |
| **Preflight Gates** | Partial (kill switch, config validation) | Full checklist before live: equity, position, API, etc. | HIGH |
| **Order Types** | Market + working orders (limit) | Market, Limit, Stop-Market, Reduce-Only, Post-Only | MEDIUM |
| **Multi-Symbol** | Hardcoded single symbol per session | Multi-symbol support with portfolio-level risk | LOW (future) |
| **Metrics/Observability** | Basic heartbeat + logs | Prometheus/StatsD metrics, structured logging, alerting | MEDIUM |
| **Test Coverage** | Good unit tests, some integration | Replay regression tests, PnL reproducibility tests | MEDIUM |

---

## 2. Target Architecture (Proposed End-State)

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                          TARGET ARCHITECTURE                                    │
├────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         CONFIG LAYER (profiles/)                         │   │
│  │   profiles/backtest.yaml   profiles/paper.yaml   profiles/live.yaml     │   │
│  │   (all inherit from profiles/base.yaml)                                  │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                      │                                          │
│                                      ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                    UNIFIED ENGINE (event-driven)                         │   │
│  │                                                                          │   │
│  │  ┌───────────────┐    ┌─────────────────┐    ┌───────────────────────┐  │   │
│  │  │  DataIngestion │───▶│ FeaturePipeline │───▶│ StrategyEngine        │  │   │
│  │  │  (Provider)    │    │ (Indicators)    │    │ (Unified Interface)   │  │   │
│  │  └───────────────┘    └─────────────────┘    └───────────┬───────────┘  │   │
│  │                                                          │              │   │
│  │                                                          ▼              │   │
│  │  ┌───────────────────────────────────────────────────────────────────┐  │   │
│  │  │                    ORDER MANAGER                                   │  │   │
│  │  │  • Order validation • Deduplication • State machine               │  │   │
│  │  └──────────────────────────────┬────────────────────────────────────┘  │   │
│  │                                 │                                       │   │
│  │                                 ▼                                       │   │
│  │  ┌───────────────────────────────────────────────────────────────────┐  │   │
│  │  │              PORTFOLIO & RISK MANAGER                              │  │   │
│  │  │  • Position sizing • Max exposure • Drawdown limits • Kill switch │  │   │
│  │  └──────────────────────────────┬────────────────────────────────────┘  │   │
│  │                                 │                                       │   │
│  └─────────────────────────────────┼───────────────────────────────────────┘   │
│                                    │                                            │
│                                    ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                     EXECUTION LAYER (Broker Abstraction)                 │   │
│  │                                                                          │   │
│  │   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────────┐   │   │
│  │   │ BacktestBroker  │   │   PaperBroker   │   │    LiveBroker       │   │   │
│  │   │ (SimulatedFills)│   │ (Paper Trading) │   │ (Bitunix/Exchange)  │   │   │
│  │   └─────────────────┘   └─────────────────┘   └─────────────────────┘   │   │
│  │                                                                          │   │
│  │   All implement BrokerProtocol with identical order interface            │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                            │
│                                    ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                          STATE & PERSISTENCE                             │   │
│  │   • SQLite (positions, orders, fills)                                    │   │
│  │   • JSONL event log (append-only audit trail)                            │   │
│  │   • Parquet (historical candles, backtest results)                       │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                    │                                            │
│                                    ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         OBSERVABILITY LAYER                              │   │
│  │   • Structured logging (JSON)  • Metrics (Prometheus/file)               │   │
│  │   • Alerting hooks             • Dashboard (optional Flask)              │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Module Responsibilities

| Module | Responsibility |
|--------|----------------|
| **DataIngestion** | Fetch/stream OHLCV, order book, trades from exchange or replay file. Normalize to `Candle`/`Tick`. |
| **FeaturePipeline** | Compute indicators (SMA, ATR, VWAP, CVD), structure levels. Stateless transforms. |
| **StrategyEngine** | Run strategy logic, emit `OrderIntent` (side, size, SL, TP). Pure function of state. |
| **OrderManager** | Convert intents → validated orders. Manage pending/working orders. Handle deduplication. |
| **PortfolioRisk** | Position limits, max loss, max leverage, correlation checks, kill switch. |
| **Broker** | Execute orders. BacktestBroker simulates; PaperBroker uses live data; LiveBroker submits to exchange. |
| **StateStore** | Persist positions, orders, equity curve. Support resume-from-checkpoint. |
| **Observability** | Structured logs, metrics export, alerting hooks. |

---

## 3. Roadmap (Phased Plan)

### Milestone Summary Table

| Phase | Milestone | Effort | Key Deliverables |
|-------|-----------|--------|------------------|
| 0 | **Foundation** | M | Unified config profiles, broker interface cleanup |
| 1 | **MVP Refactor** | L | Single engine for backtest+paper+live; same strategy code path |
| 2 | **Backtest Parity** | M | Realistic fill model, spread, latency, funding |
| 3 | **Paper Trading** | S | Paper mode with live data, state persistence, resume |
| 4 | **Live Trading** | M | Preflight gates, live broker hardening, rollback |
| 5 | **Reliability** | M | Observability, circuit breakers, chaos testing |
| 6 | **DevEx** | S | CLI polish, documentation, replay test suite |

---

### Phase 0: Foundation (Effort: M)

**Objectives:**
- Establish unified configuration system
- Clean up broker interface inconsistencies
- Set up regression test baseline

**Tasks:**
| Task | Description | DoD |
|------|-------------|-----|
| 0.1 | Create `profiles/` directory with `base.yaml`, `backtest.yaml`, `paper.yaml`, `live.yaml` | Config loads correctly per profile |
| 0.2 | Implement `ConfigLoader` that merges profile → env → CLI overrides | Unit tests pass for precedence |
| 0.3 | Audit `BrokerProtocol` — ensure both brokers implement all methods identically | `isinstance()` checks pass |
| 0.4 | Add `BacktestBroker` stub that will replace `backtest/engine.py` logic | Stub created, tests scaffolded |
| 0.5 | Snapshot current backtest results for 3 test datasets as regression baseline | Baseline stored in `tests/fixtures/` |

**Risks & Mitigations:**
- Risk: Breaking existing paper trading. Mitigation: Feature-flag new config loader.

---

### Phase 1: MVP Refactor — Unified Engine (Effort: L)

**Objectives:**
- One code path (Supervisor + Broker) for backtest, paper, live
- Strategy code unchanged between modes
- Deterministic replay

**Tasks:**
| Task | Description | DoD |
|------|-------------|-----|
| 1.1 | Create `BacktestBroker` implementing `BrokerProtocol` with simulated fills | Unit tests for fill logic |
| 1.2 | Modify `backtest` CLI command to use Supervisor + BacktestBroker | Backtest runs through Supervisor |
| 1.3 | Create `BacktestProvider` that yields candles synchronously from Parquet/CSV | Replays recorded data |
| 1.4 | Add `--profile backtest` flag to `la run` | Profile auto-selects correct broker |
| 1.5 | Ensure `Supervisor.step()` is pure (no side effects except broker calls) | State transition tests pass |
| 1.6 | Remove duplicate logic in `backtest/engine.py`, redirect to unified path | Old engine deprecated |

**Risks & Mitigations:**
- Risk: PnL divergence between old/new backtest. Mitigation: A/B test both engines, compare stats.json.

---

### Phase 2: Backtest Parity (Effort: M)

**Objectives:**
- Model real-world execution realities
- Configurable fidelity levels (fast vs realistic)

**Tasks:**
| Task | Description | DoD |
|------|-------------|-----|
| 2.1 | Implement `FillSimulator` with configurable slippage model: fixed bps, random, volume-scaled | Config selects model |
| 2.2 | Add bid/ask spread modeling: use historical spread or config default | Spread applied to fill prices |
| 2.3 | Implement partial fills for limit orders (probabilistic or volume-based) | Tests show partial fill events |
| 2.4 | Add latency injection: `execution_latency_ms` delays order processing | Configurable in profile |
| 2.5 | Integrate historical funding rates (load from CSV, apply per 8h) | Funding deducted from equity |
| 2.6 | Add intrabar resolution modes: `conservative` (worst-case), `optimistic`, `random` | Mode configurable |
| 2.7 | Create `OrderBook` stub for future L2 simulation | Interface defined |

**Fill Model Configuration:**
```yaml
# profiles/backtest.yaml
fill_model:
  slippage_model: "volume_scaled"  # fixed_bps, random, volume_scaled
  slippage_base_bps: 2.0
  spread_model: "historical"       # fixed, historical
  spread_fixed_bps: 1.0
  partial_fills: false
  latency_ms: 0                    # 0 = instant
  intrabar_mode: "conservative"    # conservative, optimistic, random

funding:
  enabled: true
  source: "data/funding_rates.csv"
```

**Risks:**
- Risk: Overfitting slippage model. Mitigation: Validate against paper trading PnL.

---

### Phase 3: Paper Trading (Effort: S)

**Objectives:**
- Paper trading with live data stream
- Full state persistence and resume
- Identical to backtest except data source

**Tasks:**
| Task | Description | DoD |
|------|-------------|-----|
| 3.1 | Ensure PaperBroker state survives restarts via SQLite checkpoint | Resume test passes |
| 3.2 | Add `--resume` flag to `la run --profile paper` | Continues from last state |
| 3.3 | Implement funding rate application from live WebSocket | Funding events logged |
| 3.4 | Add paper-to-backtest export: dump session to Parquet for replay | Export command works |
| 3.5 | Create daily equity snapshot job | Equity CSV written nightly |

**Risks:**
- Risk: State corruption on crash. Mitigation: WAL mode + fsync; backup before each session.

---

### Phase 4: Live Trading (Effort: M)

**Objectives:**
- Safe, gated live trading
- Human-in-the-loop confirmation (optional bypass)
- Disaster recovery

**Tasks:**
| Task | Description | DoD |
|------|-------------|-----|
| 4.1 | Implement `PreflightChecker` with required gates | All gates must pass |
| 4.2 | Add position reconciliation on startup (local vs exchange) | Drift detected and logged |
| 4.3 | Implement order acknowledgment tracking (submitted → acked → filled) | State machine in OrderManager |
| 4.4 | Add manual confirmation gate (enabled by default, bypass via config) | Confirmation works |
| 4.5 | Create `EmergencyShutdown` procedure: cancel all, close all, notify | Works on Ctrl+C and crash |
| 4.6 | Add max slippage protection: reject fill if slippage > threshold | Threshold configurable |
| 4.7 | Implement dead-man switch: auto-shutdown if no heartbeat for N minutes | Watchdog enhanced |

**Preflight Gates (all must pass):**
```
[x] API connectivity (ping exchange)
[x] API key permissions validated
[x] Local position == exchange position
[x] No working orders orphaned
[x] Account equity > minimum threshold
[x] Daily loss limit not exceeded
[x] Kill switch file not present
[x] Config hash matches expected (prevent stale config)
```

**Risks:**
- Risk: Ghost orders/positions. Mitigation: Always reconcile on startup.
- Risk: API rate limits. Mitigation: Rate limiter in provider (already exists, verify limits).

---

### Phase 5: Reliability & Scaling (Effort: M)

**Objectives:**
- Production-grade observability
- Chaos resilience
- Performance optimization

**Tasks:**
| Task | Description | DoD |
|------|-------------|-----|
| 5.1 | Add Prometheus metrics exporter (or file-based metrics.json) | Metrics endpoint works |
| 5.2 | Implement structured JSON logging with correlation IDs | Logs parseable |
| 5.3 | Add alerting hooks (webhook, email, Telegram) for critical events | Alert fires on kill switch |
| 5.4 | Create chaos test suite: network partition, exchange timeout, OOM | Tests in `tests/stress/` |
| 5.5 | Profile and optimize hot paths (indicator computation) | <10ms per step for 1m candles |
| 5.6 | Add memory usage guards (already have `LA_MAX_MEMORY_MB`, verify) | Process exits cleanly on limit |

---

### Phase 6: Developer Experience (Effort: S)

**Objectives:**
- Easy onboarding
- Comprehensive documentation
- Replay-based CI

**Tasks:**
| Task | Description | DoD |
|------|-------------|-----|
| 6.1 | Polish CLI: `la doctor`, `la status`, `la replay`, `la export` | All commands documented |
| 6.2 | Create `QUICKSTART.md` with 5-minute setup | New dev runs paper in 5 min |
| 6.3 | Add replay regression tests to CI (compare PnL to baseline) | CI green on main |
| 6.4 | Generate HTML backtest reports with equity curve, trade log | Report opens in browser |
| 6.5 | Create strategy template with full docstrings | Template in `strategies/template/` |

---

## 4. Backtest ↔ Live Fidelity Requirements

### 4.1 Execution Realities to Model

| Reality | Backtest Modeling | Live Handling |
|---------|-------------------|---------------|
| **Fees** | Apply maker/taker rate per fill (configurable per exchange) | Exchange deducts automatically; track in local state |
| **Slippage** | Models: fixed bps, random (0.5-1.5x base), volume-scaled | Observed slippage logged; compare to model |
| **Latency** | Inject configurable delay before fill | Measure order-to-fill latency; log for analysis |
| **Partial Fills** | Probabilistic for limits (volume-based); markets always fill 100% | Track partial fill events; aggregate to full position |
| **Spread** | Apply half-spread on entry, half on exit (configurable) | Use best bid/ask from order book or ticker |
| **Order Types** | Support market, limit, stop-market in simulation | Map to exchange order types |
| **Funding** | Apply 8h funding rate from historical data | Apply from WebSocket every 8h |
| **Queue Position** | Not modeled (assume front-of-queue for limits) | N/A — use market orders for safety |

### 4.2 Unified Order Interface

```python
@dataclass
class OrderIntent:
    """Strategy output — what we want to do."""
    side: Literal["LONG", "SHORT"]
    entry_type: Literal["market", "limit", "stop_market"]
    qty: float
    entry: Optional[float]  # None for market
    sl: float
    tp: float
    reduce_only: bool = False
    client_order_id: Optional[str] = None

@dataclass
class OrderResult:
    """Broker output — what happened."""
    status: Literal["filled", "partial", "pending", "rejected", "cancelled"]
    fill_price: Optional[float]
    fill_qty: Optional[float]
    fees: float
    latency_ms: Optional[float]
    exchange_order_id: Optional[str]
```

### 4.3 Ensuring Same Strategy Code

```python
# Strategy is pure function of state — no awareness of mode
class MyStrategy:
    def on_bar(self, state: StrategyState) -> Optional[OrderIntent]:
        # Compute signal from state.candles, state.indicators
        if self.should_enter_long(state):
            return OrderIntent(
                side="LONG",
                entry_type="market",
                qty=self.compute_size(state),
                sl=state.candles[-1].low - state.atr * 1.5,
                tp=state.candles[-1].close + state.atr * 3.0,
            )
        return None

# Engine handles mode differences:
# - BacktestBroker.execute(intent) → instant simulated fill
# - PaperBroker.execute(intent) → simulated fill with live price
# - LiveBroker.execute(intent) → submit to exchange, poll for fill
```

---

## 5. Testing & Quality Plan

### 5.1 Test Categories

| Category | Purpose | Location | Run Frequency |
|----------|---------|----------|---------------|
| **Unit** | Test individual functions (indicators, position math) | `tests/test_*.py` | Every commit |
| **Integration** | Test module interactions (Supervisor + Broker) | `tests/test_*_integration.py` | Every commit |
| **Replay** | Replay recorded sessions, verify PnL matches baseline | `tests/replay/` | Every PR |
| **Regression** | Compare backtest results to golden files | `tests/regression/` | Every PR |
| **E2E Paper** | Full paper trading session (15 min) | `tests/e2e/` | Nightly |
| **Stress** | Memory, latency, error injection | `tests/stress/` | Weekly |

### 5.2 Mocking Strategy

| Component | Mock Approach |
|-----------|---------------|
| Exchange API | `tests/fixtures/mock_responses.json` + `MockProvider` |
| WebSocket | `aiohttp` test client or recorded JSONL replay |
| Time | Inject `TimeProvider` interface; freeze in tests |
| Random | Seed via `random_seed` parameter (already supported) |

### 5.3 CI/CD Recommendations

```yaml
# .github/workflows/ci.yml additions
jobs:
  test:
    steps:
      - run: pytest tests/ -x --cov=src/laptop_agents --cov-report=xml
      - run: mypy src/laptop_agents --strict
      - run: ruff check src/

  replay-regression:
    needs: test
    steps:
      - run: python -m pytest tests/replay/ --baseline-dir=tests/fixtures/baselines/

  nightly-paper:
    schedule: [cron: '0 2 * * *']
    steps:
      - run: la run --profile paper --duration 15 --dry-run
```

### 5.4 Safety Checks Before Live Mode

```python
# src/laptop_agents/core/preflight.py
PREFLIGHT_GATES = [
    ("api_connectivity", check_api_ping),
    ("api_permissions", check_api_permissions),
    ("position_reconciliation", check_position_match),
    ("no_orphan_orders", check_no_working_orders),
    ("min_equity", lambda: equity > MIN_EQUITY_USD),
    ("daily_loss_ok", lambda: daily_loss < MAX_DAILY_LOSS_USD),
    ("kill_switch_off", lambda: not KILL_SWITCH_FILE.exists()),
    ("config_hash", check_config_hash),
]

def run_preflight() -> List[Tuple[str, bool, str]]:
    results = []
    for name, check in PREFLIGHT_GATES:
        try:
            passed = check()
            results.append((name, passed, "" if passed else "FAILED"))
        except Exception as e:
            results.append((name, False, str(e)))
    return results
```

---

## 6. Data Plan

### 6.1 Data Requirements

| Data Type | Resolution | Source | Use Case |
|-----------|------------|--------|----------|
| OHLCV (candles) | 1m | Bitunix REST/WS | Primary trading data |
| OHLCV (historical) | 1m | Bitunix REST or third-party | Backtest |
| Trades (ticks) | Real-time | WebSocket (optional) | Tick-level backtesting |
| Order book (L2) | Snapshot | REST (future) | Spread modeling |
| Funding rates | 8h | REST | Funding cost simulation |
| Mark price | Real-time | WebSocket | Liquidation checks |

### 6.2 Storage Format

```
data/
├── candles/
│   └── BTCUSDT/
│       ├── 2024-01.parquet      # Monthly Parquet files
│       ├── 2024-02.parquet
│       └── metadata.json        # Symbol info, last update
├── funding/
│   └── BTCUSDT_funding.csv      # timestamp, rate
├── replays/
│   └── session_2024-01-15.jsonl # Recorded session for replay
└── cache/
    └── latest_candles.pkl       # Hot cache for startup
```

### 6.3 Data Quality & Lookahead Prevention

| Issue | Prevention |
|-------|------------|
| **Lookahead bias** | Only access `candles[:i+1]` in backtest loop; indicators cannot peek ahead |
| **Survivorship bias** | N/A for single-symbol BTC trading |
| **Gaps/missing data** | Validate candle continuity; interpolate or skip sessions with gaps |
| **Timezone** | All timestamps in UTC; parse with `datetime.fromisoformat()` |
| **Duplicate data** | Dedupe by timestamp on ingest |

---

## 7. Security & Ops

### 7.1 Secrets Management

| Secret | Storage | Access |
|--------|---------|--------|
| API Key | `.env` file (never committed) | `os.environ["BITUNIX_API_KEY"]` |
| API Secret | `.env` file | `os.environ["BITUNIX_API_SECRET"]` |
| Webhook tokens | `.env` file | For alerting integrations |

**Best Practices:**
- `.env` in `.gitignore` (already done)
- Use `python-dotenv` for loading (already done)
- Never log secrets; scrub from error messages (test exists)
- Rotate keys periodically

### 7.2 Logging & Metrics

```python
# Structured log format
{
    "ts": "2024-01-15T10:30:00Z",
    "level": "INFO",
    "event": "order_filled",
    "trade_id": "abc123",
    "side": "LONG",
    "qty": 0.01,
    "price": 42000.0,
    "latency_ms": 150,
    "session_id": "sess_xyz"
}
```

**Metrics to Track:**
- `orders_submitted_total` (counter)
- `orders_filled_total` (counter)
- `pnl_realized_usd` (gauge)
- `position_size_usd` (gauge)
- `equity_usd` (gauge)
- `fill_latency_ms` (histogram)
- `websocket_reconnects_total` (counter)

### 7.3 Deployment Options

| Environment | Setup | Monitoring |
|-------------|-------|------------|
| **Laptop** | Direct `la run`, PowerShell wrapper | Heartbeat file, `la status` |
| **VPS** | Systemd service or Docker | Prometheus + Grafana |
| **Cloud** | AWS ECS / GCP Cloud Run | CloudWatch / Stackdriver |

**Laptop Deployment (Current):**
```powershell
# ops.ps1 wrapper handles:
# - Restart on crash
# - Log rotation
# - Heartbeat monitoring
```

### 7.4 Disaster Recovery

| Scenario | Recovery |
|----------|----------|
| Process crash | Watchdog restarts; resume from SQLite state |
| State corruption | Restore from hourly backup (`.workspace/backups/`) |
| Exchange outage | Circuit breaker halts trading; alert fires |
| Network partition | WebSocket reconnect with backoff; no new orders until healthy |
| Rogue trade | Kill switch file or env var stops all trading; manual position close |

---

## 8. One-Switch Live Mode

### 8.1 Configuration Profiles

```
config/
└── profiles/
    ├── base.yaml          # Shared defaults
    ├── backtest.yaml      # Extends base, fast simulation
    ├── paper.yaml         # Extends base, live data, no real orders
    └── live.yaml          # Extends base, real orders, strict gates
```

### 8.2 Profile Structure

```yaml
# config/profiles/base.yaml
meta:
  version: 1

symbol: BTCUSDT
timeframe: 1m

trading:
  starting_equity: 10000.0
  risk_pct: 1.0
  max_leverage: 5.0
  max_position_usd: 50000.0
  max_daily_loss_usd: 50.0

strategy:
  name: sweep_invalidation
  config_file: config/strategies/scalp_1m_sweep.json

engine:
  min_history_bars: 100
  warmup_candles: 51

logging:
  level: INFO
  format: json
```

```yaml
# config/profiles/backtest.yaml
_extends: base.yaml

mode: backtest

data:
  source: parquet
  path: data/candles/BTCUSDT/

broker:
  type: backtest
  fill_model:
    slippage_bps: 2.0
    spread_bps: 1.0
    latency_ms: 0
    partial_fills: false
    intrabar_mode: conservative

  funding:
    enabled: true
    source: data/funding/BTCUSDT_funding.csv

output:
  dir: .workspace/runs/backtest_{timestamp}
```

```yaml
# config/profiles/paper.yaml
_extends: base.yaml

mode: paper

data:
  source: websocket
  provider: bitunix

broker:
  type: paper
  state_path: .workspace/paper/broker_state.db
  fill_model:
    slippage_bps: 2.0
    spread_bps: 0.5  # Use live spread

preflight:
  enabled: false  # Paper doesn't need full gates

logging:
  level: DEBUG
```

```yaml
# config/profiles/live.yaml
_extends: base.yaml

mode: live

data:
  source: websocket
  provider: bitunix

broker:
  type: live
  confirm_orders: true  # Human confirmation gate

preflight:
  enabled: true
  required_gates:
    - api_connectivity
    - position_reconciliation
    - min_equity
    - daily_loss_ok
    - kill_switch_off

safety:
  max_slippage_bps: 10.0
  dead_man_timeout_sec: 300

logging:
  level: INFO
  alert_webhook: ${ALERT_WEBHOOK_URL}
```

### 8.3 Switching Modes

```powershell
# Backtest
la run --profile backtest --days 30

# Paper trading
la run --profile paper --duration 60

# Live trading (requires preflight pass)
la run --profile live --duration 60

# Environment override
$env:LA_PROFILE = "live"
la run --duration 60
```

### 8.4 Preflight Checklist (Live Mode)

```
╔═══════════════════════════════════════════════════════════════╗
║                    LIVE TRADING PREFLIGHT                      ║
╠═══════════════════════════════════════════════════════════════╣
║ [✓] API Connectivity          Ping: 45ms                       ║
║ [✓] API Permissions           Trade: ✓ | Withdraw: ✗           ║
║ [✓] Position Reconciliation   Local: FLAT | Exchange: FLAT     ║
║ [✓] No Orphan Orders          Working orders: 0                ║
║ [✓] Minimum Equity            $10,000.00 > $1,000.00 min       ║
║ [✓] Daily Loss OK             $0.00 < $50.00 limit             ║
║ [✓] Kill Switch               Not active                       ║
║ [✓] Config Hash               Matches expected                 ║
╠═══════════════════════════════════════════════════════════════╣
║ STATUS: ALL GATES PASSED — Ready for live trading              ║
╚═══════════════════════════════════════════════════════════════╝
```

---

## 9. Next 10 Commits — Concrete Starter Plan

| # | Commit Message | Files Changed | Effort |
|---|----------------|---------------|--------|
| 1 | `feat(config): add profile system with base/backtest/paper/live` | `config/profiles/*.yaml`, `src/laptop_agents/core/config_loader.py` | M |
| 2 | `refactor(broker): add BacktestBroker implementing BrokerProtocol` | `src/laptop_agents/backtest/backtest_broker.py` | M |
| 3 | `feat(backtest): create BacktestProvider for Parquet/CSV replay` | `src/laptop_agents/data/providers/backtest_provider.py` | S |
| 4 | `refactor(engine): route backtest through Supervisor + BacktestBroker` | `src/laptop_agents/commands/backtest.py`, `session/backtest_session.py` | L |
| 5 | `feat(fill): implement FillSimulator with configurable slippage models` | `src/laptop_agents/backtest/fill_simulator.py` | M |
| 6 | `test(regression): add PnL baseline snapshots for 3 test datasets` | `tests/fixtures/baselines/`, `tests/regression/test_pnl_match.py` | S |
| 7 | `feat(preflight): implement PreflightChecker with all live gates` | `src/laptop_agents/core/preflight.py` | M |
| 8 | `refactor(cli): add --profile flag to la run command` | `src/laptop_agents/cli.py`, `src/laptop_agents/main.py` | S |
| 9 | `feat(funding): load historical funding rates in backtest` | `src/laptop_agents/backtest/funding.py` | S |
| 10 | `docs: update ENGINEER.md with profile system and preflight docs` | `docs/ENGINEER.md` | S |

---

## Appendix A: Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| PnL divergence backtest vs live | High | High | Unified engine; A/B compare paper vs backtest |
| State corruption on crash | Medium | High | WAL mode; hourly backups; idempotent recovery |
| Exchange API changes | Medium | Medium | Version pin provider; integration tests against testnet |
| Overfitting backtest slippage | Medium | Medium | Validate slippage model against paper trading |
| Ghost positions on startup | Low | High | Always reconcile; log drift; auto-close option |
| Rate limiting | Low | Medium | Existing rate limiter; exponential backoff |
| Secret exposure | Low | Critical | Never log; scrub errors; `.env` in `.gitignore` |

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **OrderIntent** | Strategy's desired trade (before risk/validation) |
| **OrderResult** | Broker's response after execution attempt |
| **Preflight** | Checks that must pass before live trading starts |
| **Kill Switch** | Emergency halt triggered by file or env var |
| **Circuit Breaker** | Auto-halt after N errors or max loss hit |
| **WAL** | Write-Ahead Logging (SQLite durability mode) |
| **CVD** | Cumulative Volume Delta (buy vs sell pressure) |
| **R** | Risk unit (1R = amount risked per trade) |
