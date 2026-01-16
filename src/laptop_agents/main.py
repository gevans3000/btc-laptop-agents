import sys
import os
import shutil
import time
from pathlib import Path
from typing import Optional, List
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Ensure src is in sys.path
HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parent.parent.parent
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.append(str(REPO_ROOT / "src"))

from laptop_agents import __version__
from laptop_agents.core.lock_manager import LockManager
from laptop_agents.core.orchestrator import RUNS_DIR, LATEST_DIR
from laptop_agents.run import run_cli

app = typer.Typer(help="Laptop Agents Unified CLI")
console = Console()

@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Run a trading session (passes all arguments to the runner logic)"
)
def run(ctx: typer.Context):
    """Wrapper for the main run logic."""
    # ctx.args contains any extra arguments passed to the command
    exit_code = run_cli(ctx.args)
    raise typer.Exit(code=exit_code)

@app.command(help="Check current system status")
def status():
    """Check if an agent is currently running and show system vitals."""
    LOCK_FILE = REPO_ROOT / ".agent" / "lockfile.pid"
    lock = LockManager(LOCK_FILE)
    status_msg = lock.get_status()
    
    table = Table(title="System Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="magenta")
    
    if status_msg["running"]:
        table.add_row("Agent Runner", f"[green]RUNNING[/green] (PID: {status_msg['pid']})")
        # Memory info
        mem = status_msg["memory_info"]
        rss_mb = mem.get("rss", 0) / 1024 / 1024
        table.add_row("Memory Usage", f"{rss_mb:.1f} MB")
        
        # Up time
        created = status_msg["created"]
        uptime_sec = time.time() - created
        uptime_str = time.strftime("%H:%M:%S", time.gmtime(uptime_sec))
        table.add_row("Uptime", uptime_str)
    else:
        table.add_row("Agent Runner", "[yellow]STOPPED[/yellow]")
    
    # Check artifacts
    all_runs = [d for d in RUNS_DIR.iterdir() if d.is_dir() and d.name != "latest"] if RUNS_DIR.exists() else []
    table.add_row("Total Runs", str(len(all_runs)))
    
    console.print(table)

@app.command(help="Clean up old run artifacts")
def clean(days: int = typer.Option(7, help="Delete runs older than this many days")):
    """Safely delete old run directories."""
    if not RUNS_DIR.exists():
        console.print("[yellow]No runs directory found.[/yellow]")
        return
    
    now = time.time()
    deleted_count = 0
    
    for run_dir in RUNS_DIR.iterdir():
        if run_dir.is_dir() and run_dir.name != "latest":
            mtime = run_dir.stat().st_mtime
            if (now - mtime) > (days * 86400):
                console.print(f"Deleting {run_dir.name}...")
                shutil.rmtree(run_dir)
                deleted_count += 1
                
    console.print(f"[green]Cleaned up {deleted_count} old runs.[/green]")

@app.command(help="System health check (diagnostic)")
def doctor():
    """Verify system readiness and environment."""
    console.print("[bold blue]Laptop Agents Doctor[/bold blue]\n")
    
    checks = [
        ("Python Version", sys.version.split()[0], ">=3.10"),
        ("Repo Root", str(REPO_ROOT), "exists"),
        (".env file", "exists" if (REPO_ROOT / ".env").exists() else "MISSING", "required"),
        ("Config Dir", "exists" if (REPO_ROOT / "config").exists() else "MISSING", "required"),
        ("Runs Dir", "exists" if RUNS_DIR.exists() else "missing (will be created)", "optimal"),
    ]
    
    table = Table(show_header=True, header_style="bold")
    table.add_column("Check")
    table.add_column("Value")
    table.add_column("Expected")
    table.add_column("Result")
    
    for label, val, exp in checks:
        result = "[green]PASS[/green]" if val != "MISSING" else "[red]FAIL[/red]"
        table.add_row(label, val, exp, result)
        
    console.print(table)

# Import and attach commands from the old cli.py to maintain parity
try:
    from laptop_agents import cli as old_cli
    # This is a bit hacky but keeps the code in cli.py active
    app.command(name="debug-feeds")(old_cli.debug_feeds)
    app.command(name="run-mock")(old_cli.run_mock)
    app.command(name="replay")(old_cli.run_live_history) # Mapping replay or live-history
    app.command(name="report")(old_cli.report)
    app.command(name="journal-tail")(old_cli.journal_tail)
except ImportError:
    pass

@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", callback=lambda v: (console.print(f"la {__version__}") or raise_(typer.Exit())) if v else None,
        is_eager=True, help="Show version and exit"
    )
):
    pass

def raise_(ex):
    raise ex

if __name__ == "__main__":
    app()
