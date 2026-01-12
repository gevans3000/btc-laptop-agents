# API Reference

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

## Support Modules

### `laptop_agents.agents.supervisor.Supervisor`
Orchestrates agent pipeline.
- `step(state, candle, skip_broker=False)` → State

### `laptop_agents.resilience.TradingCircuitBreaker`
Safety mechanism for drawdown limits.
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
