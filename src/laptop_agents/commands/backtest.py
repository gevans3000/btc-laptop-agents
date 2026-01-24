import typer
import os
from rich.console import Console
from laptop_agents.constants import DEFAULT_SYMBOL
from laptop_agents.core.config import load_session_config
from laptop_agents.core.legacy import run_legacy_orchestration

console = Console()


def main(
    symbol: str = typer.Option(DEFAULT_SYMBOL, help="Symbol to backtest"),
    days: int = typer.Option(1, help="Number of days for backtest"),
    interval: str = typer.Option("1m", help="Candle interval"),
    risk_pct: float = typer.Option(1.0, help="Risk percentage per trade"),
    leverage: float = typer.Option(1.0, "--leverage", help="Max leverage"),
    stop_bps: float = typer.Option(30.0, help="Stop loss in basis points"),
    tp_r: float = typer.Option(1.5, help="Take profit R-ratio"),
    show: bool = typer.Option(True, help="Show summary report after run"),
):
    """Run a backtest session."""
    symbol = symbol.upper().replace("/", "").replace("-", "")

    # Calculate backtest size (roughly)
    # 1 day = 1440 minutes
    minutes = days * 1440

    overrides = {
        "symbol": symbol,
        "interval": interval,
        "risk_pct": risk_pct,
        "max_leverage": leverage,
        "stop_bps": stop_bps,
        "tp_r": tp_r,
        "backtest": minutes,
        "mode": "backtest",
    }

    try:
        load_session_config(
            strategy_name=os.environ.get("LA_STRATEGY", "default"), overrides=overrides
        )
    except Exception as e:
        console.print(f"[red]CONFIG ERROR: {e}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[cyan]Starting backtest for {symbol} ({days} days)...[/cyan]")

    ret = run_legacy_orchestration(
        mode="backtest",
        symbol=symbol,
        interval=interval,
        source="bitunix",  # Force bitunix to fetch historical data
        limit=minutes,
        fees_bps=2.0,
        slip_bps=0.5,
        risk_pct=risk_pct,
        stop_bps=stop_bps,
        tp_r=tp_r,
        max_leverage=leverage,
        intrabar_mode="conservative",
        backtest_mode="position",
    )

    if show:
        from laptop_agents.core.orchestrator import LATEST_DIR

        summary_path = LATEST_DIR / "summary.html"
        if summary_path.exists():
            import webbrowser

            webbrowser.open(f"file:///{summary_path.resolve()}")

    raise typer.Exit(code=ret)
