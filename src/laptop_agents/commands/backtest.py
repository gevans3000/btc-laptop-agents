import typer
from rich.console import Console
from laptop_agents.constants import DEFAULT_SYMBOL

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

    from laptop_agents.core.config_loader import load_profile
    from laptop_agents.session.backtest_session import run_backtest_session
    import asyncio

    overrides = {
        "symbol": symbol,
        "timeframe": interval,
        "trading": {
            "risk_pct": risk_pct,
            "max_leverage": leverage,
        },
    }

    config = load_profile("backtest", cli_overrides=overrides)

    console.print(f"[cyan]Starting backtest for {symbol} ({days} days)...[/cyan]")

    try:
        stats = asyncio.run(run_backtest_session(config))
        console.print("[green]Backtest Complete![/green]")
        console.print(f"Net PnL: [bold]${stats['net_pnl']:.2f}[/bold]")
        console.print(f"Trades: {stats['total_trades']}")
        success = True
        msg = "Backtest finished successfully"
    except Exception as e:
        console.print(f"[red]BACKTEST ERROR: {e}[/red]")
        import traceback

        traceback.print_exc()
        success = False
        msg = str(e)

    console.print(msg)

    if show:
        from laptop_agents.core.orchestrator import LATEST_DIR

        summary_path = LATEST_DIR / "summary.html"
        if summary_path.exists():
            import webbrowser

            webbrowser.open(f"file:///{summary_path.resolve()}")

    raise typer.Exit(code=0 if success else 1)
