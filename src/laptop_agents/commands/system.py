import sys
import os
import shutil
import time
import typer
from rich.console import Console
from rich.table import Table
from laptop_agents.constants import AGENT_PID_FILE, REPO_ROOT
from laptop_agents.core.lock_manager import LockManager
from laptop_agents.core.events import RUNS_DIR

console = Console()
LOCK_FILE = AGENT_PID_FILE


def status():
    """Check if an agent is currently running and show system vitals."""
    lock = LockManager(LOCK_FILE)
    status_msg = lock.get_status()

    table = Table(title="System Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="magenta")

    # Kill Switch Check (Single Source of Truth: Environment)
    kill_active = os.environ.get("LA_KILL_SWITCH", "FALSE").upper() == "TRUE"
    ks_status = "[red]ACTIVE (BLOCKING)[/red]" if kill_active else "[green]OFF[/green]"
    table.add_row("Kill Switch", ks_status)

    if status_msg["running"]:
        table.add_row(
            "Agent Runner", f"[green]RUNNING[/green] (PID: {status_msg['pid']})"
        )
        mem = status_msg["memory_info"]
        rss_mb = mem.get("rss", 0) / 1024 / 1024
        table.add_row("Memory Usage", f"{rss_mb:.1f} MB")

        created = status_msg["created"]
        uptime_sec = time.time() - created
        uptime_str = time.strftime("%H:%M:%S", time.gmtime(uptime_sec))
        table.add_row("Uptime", uptime_str)
    else:
        table.add_row("Agent Runner", "[yellow]STOPPED[/yellow]")

    all_runs = (
        [d for d in RUNS_DIR.iterdir() if d.is_dir() and d.name != "latest"]
        if RUNS_DIR.exists()
        else []
    )
    table.add_row("Total Runs", str(len(all_runs)))

    console.print(table)


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


def doctor(
    fix: bool = typer.Option(
        False, "--fix", help="Attempt to fix missing directories and environment"
    ),
):
    """Verify system readiness and environment."""
    console.print("[bold blue]Laptop Agents Doctor[/bold blue]\n")

    if fix:
        workspace_dir = REPO_ROOT / ".workspace"
        for sub in ["runs", "logs", "paper", "locks"]:
            (workspace_dir / sub).mkdir(parents=True, exist_ok=True)
        console.print("[green]Verified .workspace/ structure.[/green]")

        env_path = REPO_ROOT / ".env"
        env_example = REPO_ROOT / ".env.example"
        if not env_path.exists() and env_example.exists():
            shutil.copy2(env_example, env_path)
            console.print(
                "[yellow]! Created .env from .env.example. PLEASE EDIT IT.[/yellow]"
            )

    bitunix_status = "OK"
    live_mode = (
        os.environ.get("LA_EXECUTION_MODE") == "live"
        or os.environ.get("LA_SOURCE") == "bitunix"
    )
    if live_mode:
        api_key = os.environ.get("BITUNIX_API_KEY")
        api_secret = os.environ.get("BITUNIX_API_SECRET")
        if not api_key or not api_secret:
            bitunix_status = "MISSING"

    checks = [
        ("Python Version", sys.version.split()[0], ">=3.10"),
        ("Repo Root", str(REPO_ROOT), "exists"),
        (
            ".env file",
            "exists" if (REPO_ROOT / ".env").exists() else "MISSING",
            "required",
        ),
        (
            "Config Dir",
            "exists" if (REPO_ROOT / "config").exists() else "MISSING",
            "required",
        ),
        (
            "Workspace",
            "exists" if (REPO_ROOT / ".workspace").exists() else "MISSING",
            "required",
        ),
        (
            "Pyproject.toml",
            "exists" if (REPO_ROOT / "pyproject.toml").exists() else "MISSING",
            "required",
        ),
        ("Bitunix Keys", bitunix_status, "required for live"),
    ]

    table = Table(show_header=True, header_style="bold")
    table.add_column("Check")
    table.add_column("Value")
    table.add_column("Expected")
    table.add_column("Result")

    for label, val, exp in checks:
        if val == "MISSING":
            result = "[red]FAIL[/red]"
        else:
            result = "[green]PASS[/green]"
        table.add_row(label, str(val), exp, result)

    console.print(table)

    # 1. Version Consistency Check
    console.print("\n[bold]Checking Version Consistency...[/bold]")
    pyproject_ver = "Unknown"
    init_ver = "Unknown"

    # Parse pyproject.toml
    pyproject_path = REPO_ROOT / "pyproject.toml"
    if pyproject_path.exists():
        with open(pyproject_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("version ="):
                    pyproject_ver = line.split("=")[1].strip().strip('"').strip("'")
                    break

    # Parse __init__.py
    init_path = REPO_ROOT / "src/laptop_agents/__init__.py"
    if init_path.exists():
        with open(init_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("__version__ ="):
                    init_ver = line.split("=")[1].strip().strip('"').strip("'")
                    break

    if pyproject_ver == init_ver and pyproject_ver != "Unknown":
        console.print(f"[green]PASS[/green] Versions match: {pyproject_ver}")
    else:
        console.print(
            f"[red]FAIL[/red] Version mismatch! pyproject.toml: {pyproject_ver}, __init__.py: {init_ver}"
        )

    # 2. Live Connectivity Check (if keys present)
    api_key = os.environ.get("BITUNIX_API_KEY")
    api_secret = os.environ.get("BITUNIX_API_SECRET")

    if bitunix_status != "MISSING" and api_key and api_secret:
        console.print("\n[bold]Checking Bitunix Connectivity...[/bold]")
        try:
            # Lazy import to avoid hard dependency at module level
            from laptop_agents.data.providers.bitunix_futures import (
                BitunixFuturesProvider,
            )

            api_key = os.environ.get("BITUNIX_API_KEY")
            api_secret = os.environ.get("BITUNIX_API_SECRET")

            provider = BitunixFuturesProvider(
                symbol="BTCUSDT", api_key=api_key, secret_key=api_secret
            )

            # Authenticated check (positions)
            with console.status("[bold green]Testing authenticated API..."):
                positions = provider.get_pending_positions()
                console.print(
                    f"[green]PASS[/green] Authenticated API (Found {len(positions)} positions)"
                )

        except Exception as e:
            console.print(f"[red]FAIL[/red] Connectivity check failed: {e}")

    if not fix and any(c[1] == "MISSING" for c in checks):
        console.print(
            "\n[yellow]Hint: Run 'la doctor --fix' to automate setup.[/yellow]"
        )
