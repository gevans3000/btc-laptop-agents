from __future__ import annotations
from typing import Any, Dict
from laptop_agents.data.providers.backtest_provider import BacktestProvider
from laptop_agents.backtest.backtest_broker import BacktestBroker
from laptop_agents.agents.supervisor import Supervisor
from laptop_agents.agents.state import State
from laptop_agents.core.logger import logger


async def run_backtest_session(config: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a backtest session using the unified Supervisor + BacktestBroker path."""
    data_path = config.get("data", {}).get("path", "data/candles/BTCUSDT/")
    symbol = config.get("symbol", "BTCUSDT")

    provider = BacktestProvider(data_path, symbol=symbol)
    broker = BacktestBroker(
        symbol=symbol,
        fees_bps=config.get("broker", {}).get("fees_bps", 2.0),
        starting_equity=config.get("trading", {}).get("starting_equity", 10000.0),
        fill_simulator_config=config.get("broker", {}).get("fill_model", {}),
    )

    # We pass the config to Supervisor. Supervisor expects a specific structure.
    # We might need to adapt config if Supervisor expects keys at a certain depth.
    supervisor = Supervisor(provider, config, broker=broker)

    state = State(instrument=symbol, timeframe=config.get("timeframe", "1m"))

    logger.info("Starting backtest warmup...")
    warmup_n = config.get("engine", {}).get("warmup_candles", 51)
    for candle in provider.history(warmup_n):
        state = supervisor.step(state, candle, skip_broker=True)

    logger.info("Running backtest simulation...")
    # listen() yields after history
    async for candle in provider.listen(start_after=warmup_n):
        # Inject equity into order if needed by supervisor
        if state.order and state.order.get("go"):
            state.order["equity"] = broker.current_equity
            state.order["risk_pct"] = config.get("trading", {}).get("risk_pct", 1.0)
            state.order["size_mult"] = 1.0  # Default
            state.order["rr_min"] = config.get("trading", {}).get("rr_min", 1.5)

        state = supervisor.step(state, candle)

    return generate_backtest_stats(broker)


def generate_backtest_stats(broker: BacktestBroker) -> Dict[str, Any]:
    """Calculate summary statistics from the backtest run."""
    trades = [e for e in broker.order_history if e["type"] == "exit"]
    net_pnl = broker.current_equity - broker.starting_equity

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]

    win_rate = len(wins) / len(trades) if trades else 0.0

    stats = {
        "starting_equity": broker.starting_equity,
        "final_equity": broker.current_equity,
        "net_pnl": net_pnl,
        "total_trades": len(trades),
        "win_rate": win_rate,
        "wins": len(wins),
        "losses": len(losses),
    }

    logger.info(f"Backtest Finished: Net PnL = ${net_pnl:.2f} ({len(trades)} trades)")
    return stats
