# Strategy Catalog

| Name | File | Timeframe | Description |
| :--- | :--- | :--- | :--- |
| Scalp 1m Sweep | `scalp_1m_sweep.json` | 1m | Liquidity sweep + VWAP reclaim |
| Default | `default.json` | 1m | Baseline conservative settings |

## Usage

```powershell
# Run a specific strategy
python -m laptop_agents.run --strategy scalp_1m_sweep --mode backtest --source mock --backtest 1000

# Run with default strategy (fallback)
python -m laptop_agents.run --mode live-session --source bitunix --duration 10
```

## Adding a New Strategy

1. Copy an existing file in `config/strategies/`.
2. Rename it to `your_strategy_name.json`.
3. Edit the `meta`, `setups`, and `risk` sections.
4. Add an entry to this catalog.
