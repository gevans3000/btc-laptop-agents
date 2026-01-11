# API Reference

## Core Modules

### `laptop_agents.paper.broker.PaperBroker`
Simulated broker for backtesting and paper trading.

**Methods**:
- `on_candle(candle, order)` → Dict with fills/exits
- `get_unrealized_pnl(price)` → float
- `_try_fill(candle, order)` → Optional fill event
- `_check_exit(candle)` → Optional exit event

### `laptop_agents.execution.bitunix_broker.BitunixBroker`
Live broker for Bitunix exchange.

**Methods**:
- Same as PaperBroker
- Syncs position state with exchange

### `laptop_agents.agents.supervisor.Supervisor`
Orchestrates agent pipeline.

**Methods**:
- `step(state, candle, skip_broker=False)` → State

### `laptop_agents.resilience.TradingCircuitBreaker`
Safety mechanism for drawdown limits.

**Methods**:
- `set_starting_equity(equity)`
- `update_equity(equity, trade_pnl)`
- `is_tripped()` → bool
- `get_status()` → dict

## CLI Arguments

| Arg | Default | Description |
|-----|---------|-------------|
| `--mode` | backtest | orchestrated, backtest, live |
| `--source` | mock | mock, bitunix |
| `--symbol` | BTCUSDT | BTCUSD, BTCUSDT, ETHUSD |
| `--interval` | 1m | 1m, 5m, 15m, 1h |
| `--limit` | 100 | Number of candles |
| `--risk-pct` | 1.0 | Risk per trade (%) |
| `--execution-mode` | paper | paper, live |
| `--dry-run` | false | Log orders without executing |
