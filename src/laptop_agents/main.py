import sys
import os
from typing import Optional
import typer
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

from laptop_agents import __version__  # noqa: E402
from laptop_agents.commands import lifecycle, system, session, backtest  # noqa: E402

console = Console(force_terminal=True)
app = typer.Typer(help="Laptop Agents Unified CLI")

# Register commands
app.command(help="Start a trading session (supports background execution)")(
    lifecycle.start
)
app.command(help="Stop any running trading session")(lifecycle.stop)
app.command(help="Watch and supervisor an agent session (auto-restart on crash)")(
    lifecycle.watch
)

app.command(help="Check current system status")(system.status)
app.command(help="Clean up old run artifacts")(system.clean)
app.command(help="System health check (diagnostic)")(system.doctor)
app.command(name="watchdog", help="Check if running agent is stuck")(
    system.verify_agent_health
)


@app.command(
    name="auditor", help="Run 'Shadow Auditor' to verify agent events in real-time"
)
def run_auditor(
    lag: int = typer.Option(10, help="Number of steps/events to lag behind"),
    workspace: str = typer.Option(".workspace", help="Path to workspace directory"),
):
    import asyncio
    from pathlib import Path
    from laptop_agents.agents.auditor import AuditorAgent

    # Resolve workspace path
    ws_path = Path(workspace).absolute()
    if not ws_path.exists():
        ws_path = Path(os.getcwd()) / workspace

    auditor = AuditorAgent(ws_path, lag_events=lag)
    try:
        asyncio.run(auditor.run())
    except KeyboardInterrupt:
        console.print("[yellow]Auditor stopped.[/yellow]")


app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Run a trading session (passes all arguments to the runner logic)",
)(session.run)
app.command(name="backtest", help="Run a backtest on historical data")(backtest.main)


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    from laptop_agents.core.logger import logger, write_alert

    logger.critical(
        "Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback)
    )
    write_alert(f"CRITICAL: Unhandled exception: {exc_value}")


sys.excepthook = handle_exception


def version_callback(value: bool) -> None:
    if value:
        console.print(f"la {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
) -> None:
    pass


if __name__ == "__main__":
    app()
