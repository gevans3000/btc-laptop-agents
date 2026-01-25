# Next AI Instructions — BTC Laptop Agents Roadmap Execution

> **Purpose**: This file provides structured instructions for an AI agent to autonomously execute the development roadmap.
> **Reference**: See [DEVELOPMENT_ROADMAP.md](DEVELOPMENT_ROADMAP.md) for full context.

---

## Current State Summary

The BTC Laptop Agents repo is a functional paper/live trading system for Bitcoin (Bitunix exchange). The main gap is that **backtesting uses separate code** (`backtest/engine.py`) from the live trading pipeline (`Supervisor` + `Broker`), which creates PnL divergence risk.

**Goal**: Unify the engine so backtest, paper, and live all use the same `Supervisor.step()` → `Broker.on_candle()` code path.

---

## Execution Order (Next 10 Commits)

Work through these commits **in order**. Each commit should be atomic and pass all tests.

### Commit 1: Profile Configuration System

**Task**: Create a profile-based configuration system.

**Steps**:
1. Create directory `config/profiles/`
2. Create `config/profiles/base.yaml`:
   ```yaml
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
   engine:
     min_history_bars: 100
     warmup_candles: 51
   logging:
     level: INFO
   ```
3. Create `config/profiles/backtest.yaml`, `paper.yaml`, `live.yaml` that extend base
4. Create `src/laptop_agents/core/config_loader.py`:
   - Function `load_profile(profile_name: str) -> dict`
   - Merge logic: profile extends base, env overrides profile, CLI overrides all
   - Handle `_extends` key for inheritance
5. Add unit tests in `tests/test_config_loader.py`

**Definition of Done**:
- `load_profile("backtest")` returns merged config
- Tests pass for precedence: base < profile < env < CLI
- No regressions in existing tests

---

### Commit 2: BacktestBroker Implementation

**Task**: Create a `BacktestBroker` that implements `BrokerProtocol`.

**Steps**:
1. Create `src/laptop_agents/backtest/backtest_broker.py`
2. Copy fill logic from `paper/broker.py` (they should be similar)
3. Key differences from PaperBroker:
   - No SQLite persistence (in-memory only)
   - No working order queue (instant fills or skip)
   - Configurable `FillSimulator` (created in later commit)
4. Implement all methods from `BrokerProtocol`:
   - `on_candle(candle, order, tick) -> Dict[str, Any]`
   - `on_tick(tick) -> Dict[str, Any]` (no-op for backtest)
   - `get_unrealized_pnl(current_price) -> float`
   - `shutdown() -> None`
   - `save_state() -> None` (no-op)
   - `close_all(current_price) -> List[Dict]`
5. Add tests in `tests/test_backtest_broker.py`

**Definition of Done**:
- `isinstance(BacktestBroker(...), BrokerProtocol)` returns True
- Unit tests for fill, SL, TP logic pass
- Uses same slippage/fee application as PaperBroker

---

### Commit 3: BacktestProvider for Historical Data

**Task**: Create a data provider that yields candles from Parquet/CSV files.

**Steps**:
1. Create `src/laptop_agents/data/providers/backtest_provider.py`
2. Implement `BacktestProvider` class:
   ```python
   class BacktestProvider:
       def __init__(self, data_path: Path, symbol: str = "BTCUSDT"):
           ...

       def history(self, n: int = 200) -> List[Candle]:
           """Return first n candles for warmup."""
           ...

       async def listen(self) -> AsyncGenerator[Candle, None]:
           """Yield candles one by one (after warmup)."""
           ...

       def get_instrument_info(self, symbol: str) -> dict:
           """Return tick size, lot size, etc."""
           ...
   ```
3. Support both Parquet and CSV input
4. Add sample test data in `tests/fixtures/sample_candles.csv`
5. Add tests in `tests/test_backtest_provider.py`

**Definition of Done**:
- Provider loads candles from file
- `history()` returns warmup candles
- `listen()` yields remaining candles
- Implements `Provider` protocol from `data/provider_protocol.py`

---

### Commit 4: Route Backtest Through Supervisor

**Task**: Make the `la backtest` command use `Supervisor` + `BacktestBroker` instead of `backtest/engine.py`.

**Steps**:
1. Create `src/laptop_agents/session/backtest_session.py`:
   ```python
   async def run_backtest_session(config: dict) -> dict:
       provider = BacktestProvider(config["data"]["path"])
       broker = BacktestBroker(...)
       supervisor = Supervisor(provider, config, broker=broker)

       # Warmup
       state = State()
       for candle in provider.history():
           state = supervisor.step(state, candle, skip_broker=True)

       # Main loop
       async for candle in provider.listen():
           state = supervisor.step(state, candle)

       return generate_stats(broker)
   ```
2. Modify `src/laptop_agents/commands/backtest.py` to call `run_backtest_session`
3. Keep old `backtest/engine.py` for now (deprecate later)
4. Add A/B comparison test: old engine vs new engine on same data

**Definition of Done**:
- `la backtest --days 1` works with new engine
- PnL within 5% of old engine (slippage differences expected)
- Old engine still available via `--legacy` flag

---

### Commit 5: FillSimulator with Configurable Slippage

**Task**: Create a modular fill simulator for realistic backtest execution.

**Steps**:
1. Create `src/laptop_agents/backtest/fill_simulator.py`:
   ```python
   class FillSimulator:
       def __init__(self, config: dict):
           self.slippage_model = config.get("slippage_model", "fixed_bps")
           self.slippage_bps = config.get("slippage_bps", 2.0)
           self.spread_bps = config.get("spread_bps", 1.0)
           self.latency_ms = config.get("latency_ms", 0)

       def apply_slippage(self, price: float, side: str, is_entry: bool) -> float:
           ...

       def apply_spread(self, price: float, side: str, is_entry: bool) -> float:
           ...

       def should_fill(self, order: dict, candle: Candle) -> bool:
           """For limit orders: check if price was touched."""
           ...
   ```
2. Slippage models:
   - `fixed_bps`: Always apply configured bps
   - `random`: Apply 0.5x to 1.5x of base bps
   - `volume_scaled`: Higher slippage for larger orders
3. Integrate into `BacktestBroker`
4. Add tests for each slippage model

**Definition of Done**:
- FillSimulator is used by BacktestBroker
- Config selects slippage model
- Tests verify correct application

---

### Commit 6: Regression Test Baselines

**Task**: Create PnL baseline snapshots for regression testing.

**Steps**:
1. Create test datasets in `tests/fixtures/baselines/`:
   - `dataset_1.csv` (trending market, 1 week)
   - `dataset_2.csv` (ranging market, 1 week)
   - `dataset_3.csv` (high volatility, 3 days)
2. Run backtest on each, save results:
   - `dataset_1_expected.json` with `{"net_pnl": ..., "trades": ..., "max_dd": ...}`
3. Create `tests/regression/test_pnl_match.py`:
   ```python
   @pytest.mark.parametrize("dataset", ["dataset_1", "dataset_2", "dataset_3"])
   def test_pnl_matches_baseline(dataset):
       result = run_backtest(f"tests/fixtures/baselines/{dataset}.csv")
       expected = load_json(f"tests/fixtures/baselines/{dataset}_expected.json")
       assert abs(result["net_pnl"] - expected["net_pnl"]) < 0.01
   ```
4. Add to CI workflow

**Definition of Done**:
- 3 baseline datasets exist
- Regression tests pass
- CI runs regression tests on every PR

---

### Commit 7: Preflight Checker for Live Mode

**Task**: Implement preflight gates that must pass before live trading.

**Steps**:
1. Create `src/laptop_agents/core/preflight.py`:
   ```python
   from dataclasses import dataclass
   from typing import List, Tuple, Callable

   @dataclass
   class PreflightResult:
       name: str
       passed: bool
       message: str

   PREFLIGHT_GATES: List[Tuple[str, Callable[[], bool]]] = [
       ("api_connectivity", check_api_connectivity),
       ("position_reconciliation", check_position_match),
       ("min_equity", check_min_equity),
       ("daily_loss_ok", check_daily_loss),
       ("kill_switch_off", check_kill_switch),
   ]

   def run_preflight(config: dict) -> List[PreflightResult]:
       ...

   def all_gates_passed(results: List[PreflightResult]) -> bool:
       return all(r.passed for r in results)
   ```
2. Implement each check function
3. Display formatted preflight table in CLI
4. Block live trading if any gate fails
5. Add tests with mocked API responses

**Definition of Done**:
- All gates implemented
- Pretty CLI output shows pass/fail
- Live mode blocked if preflight fails
- Tests cover each gate

---

### Commit 8: Add --profile Flag to CLI

**Task**: Enable profile selection via CLI flag.

**Steps**:
1. Modify `src/laptop_agents/cli.py`:
   - Add `--profile` option to `run` command
   - Valid values: `backtest`, `paper`, `live`
   - Default: `paper`
2. Load profile config via `load_profile()`
3. Merge with strategy config and CLI overrides
4. Pass unified config to session runner
5. Add help text explaining profile system

**Definition of Done**:
- `la run --profile backtest` uses backtest config
- `la run --profile live` triggers preflight
- `la run --profile paper` uses paper config (default)
- Help text documents profiles

---

### Commit 9: Historical Funding Rates in Backtest

**Task**: Load and apply funding rates during backtest.

**Steps**:
1. Create `src/laptop_agents/backtest/funding.py`:
   ```python
   class FundingLoader:
       def __init__(self, csv_path: Path):
           self.rates = self._load(csv_path)  # {timestamp: rate}

       def get_rate_at(self, ts: str) -> Optional[float]:
           """Return funding rate if 8h boundary crossed."""
           ...
   ```
2. Modify `BacktestBroker` to call `broker.apply_funding(rate, ts)` at 8h intervals
3. Create sample funding data in `data/funding/BTCUSDT_funding.csv`
4. Add config option to enable/disable funding in backtest
5. Add tests verifying funding is applied

**Definition of Done**:
- Funding rates loaded from CSV
- Applied every 8h during backtest
- Equity correctly reduced by funding cost
- Can be disabled via config

---

### Commit 10: Documentation Update

**Task**: Update ENGINEER.md with profile system and preflight documentation.

**Steps**:
1. Add section "Profile Configuration" to ENGINEER.md:
   - Explain base/backtest/paper/live profiles
   - Show config precedence
   - Example commands
2. Add section "Preflight Checks" to ENGINEER.md:
   - List all gates
   - Explain how to bypass for testing
   - Document kill switch
3. Update Quick Start with profile examples
4. Add troubleshooting entries for common preflight failures

**Definition of Done**:
- ENGINEER.md updated
- Profile system fully documented
- Preflight gates documented
- Examples work as shown

---

## Testing Commands

After each commit, run:
```powershell
# Unit tests
pytest tests/ -x -v

# Type checking
mypy src/laptop_agents --strict

# Linting
ruff check src/

# Full test suite
.\testall.ps1
```

---

## Key Files to Reference

| File | Purpose |
|------|---------|
| `src/laptop_agents/core/protocols.py` | BrokerProtocol interface |
| `src/laptop_agents/paper/broker.py` | Reference implementation |
| `src/laptop_agents/agents/supervisor.py` | Main trading loop |
| `src/laptop_agents/data/provider_protocol.py` | Provider interface |
| `config/defaults.yaml` | Default trading config |
| `config/strategies/default.json` | Strategy config structure |

---

## Safety Notes

1. **Never commit secrets** — `.env` is in `.gitignore`
2. **Run tests before committing** — `pytest tests/ -x`
3. **Check types** — `mypy src/laptop_agents`
4. **Live mode requires preflight** — Never bypass in production
5. **Kill switch** — Create `LA_KILL_SWITCH=TRUE` env var to halt trading

---

## Questions to Ask If Stuck

1. How does `PaperBroker._try_fill()` handle slippage?
2. What is the structure of a `Candle` object?
3. How does `Supervisor.step()` return order decisions?
4. What events does `BrokerProtocol.on_candle()` return?
5. How is state persisted in `broker_state.db`?

Use `finder` or `Grep` to locate answers in the codebase.
