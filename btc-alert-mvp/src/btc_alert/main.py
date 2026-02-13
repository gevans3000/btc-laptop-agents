import typer

from btc_alert.pipeline import run_pipeline

app = typer.Typer(help="BTC alert MVP CLI")


@app.callback()
def main() -> None:
    """BTC alert command group."""


@app.command("run")
def run(
    interval: int = typer.Option(300, "--interval", help="Polling interval in seconds."),
    symbol: str = typer.Option("BTCUSDT", "--symbol", help="Exchange symbol."),
) -> None:
    """Run the alert loop."""
    run_pipeline(symbol=symbol, interval=interval)


if __name__ == "__main__":
    app()
