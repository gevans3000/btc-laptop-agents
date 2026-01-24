import sys
import time
import subprocess
import psutil
import typer
from rich.console import Console
from laptop_agents.constants import AGENT_PID_FILE, REPO_ROOT, DEFAULT_SYMBOL

console = Console()


def start(
    mode: str = typer.Option("live-session", help="Mode: live-session, backtest, etc."),
    execution_mode: str = typer.Option("paper", help="paper or live"),
    symbol: str = typer.Option(DEFAULT_SYMBOL, help="Symbol to trade"),
    source: str = typer.Option(None, help="Market data source: mock or bitunix"),
    detach: bool = typer.Option(False, "--detach", help="Run in background"),
):
    """Launch a session and manage PID."""
    if AGENT_PID_FILE.exists():
        try:
            old_pid = int(AGENT_PID_FILE.read_text().strip())
            if psutil.pid_exists(old_pid):
                console.print(
                    f"[red]Error: Agent already running (PID: {old_pid})[/red]"
                )
                return
        except Exception:
            pass

    resolved_source = source or ("bitunix" if mode == "live-session" else "mock")

    cmd = [
        sys.executable,
        "-m",
        "laptop_agents",
        "run",
        "--mode",
        mode,
        "--execution-mode",
        execution_mode,
        "--symbol",
        symbol,
        "--source",
        resolved_source,
        "--async",
    ]

    if detach:
        console.print(
            f"[green]Starting agent in background (mode={mode}, {execution_mode})...[/green]"
        )
        if sys.platform == "win32":
            proc = subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                cwd=str(REPO_ROOT),
            )
        else:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                cwd=str(REPO_ROOT),
            )
        AGENT_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        AGENT_PID_FILE.write_text(str(proc.pid))
        console.print(f"[bold green]Agent started with PID: {proc.pid}[/bold green]")
    else:
        try:
            AGENT_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
            proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT))
            AGENT_PID_FILE.write_text(str(proc.pid))
            proc.wait()
        finally:
            if AGENT_PID_FILE.exists():
                AGENT_PID_FILE.unlink()


def stop():
    """Stop a running session using the PID file (single source of truth)."""
    pid = None
    if AGENT_PID_FILE.exists():
        try:
            pid = int(AGENT_PID_FILE.read_text().strip())
        except Exception:
            pass

    if pid and psutil.pid_exists(pid):
        try:
            p = psutil.Process(pid)
            console.print(f"Stopping PID {pid}...")
            p.terminate()
            try:
                p.wait(timeout=5)
            except psutil.TimeoutExpired:
                console.print("[yellow]Forcing kill...[/yellow]")
                p.kill()
            if AGENT_PID_FILE.exists():
                AGENT_PID_FILE.unlink()
            console.print("[green]Stopped.[/green]")
            return
        except psutil.NoSuchProcess:
            pass

    if AGENT_PID_FILE.exists():
        # Stale PID file (process not found). Clean it up to unblock subsequent runs.
        try:
            AGENT_PID_FILE.unlink()
        except Exception:
            pass

    console.print("[red]No running agent found (missing/stale PID file).[/red]")


def watch(
    mode: str = typer.Option("live-session", help="Mode: live-session, backtest, etc."),
    execution_mode: str = typer.Option("paper", help="paper or live"),
    symbol: str = typer.Option(DEFAULT_SYMBOL, help="Symbol to trade"),
    source: str = typer.Option(None, help="Market data source: mock or bitunix"),
    duration: int = typer.Option(10, help="Duration in minutes"),
):
    """Monitor a session; if it exits with a non-zero code, wait 10s and restart."""
    LOGS_DIR = REPO_ROOT / ".workspace" / "logs"
    log_file = LOGS_DIR / "supervisor.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    def log_restart(msg: str):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a") as f:
            f.write(f"{ts} {msg}\n")
        console.print(f"[bold yellow]{ts} {msg}[/bold yellow]")

    resolved_source = source or ("bitunix" if mode == "live-session" else "mock")

    log_restart(
        f"Supervisor started for {symbol} ({mode}, {execution_mode}, {resolved_source})"
    )

    while True:
        try:
            cmd = [
                sys.executable,
                "-m",
                "laptop_agents",
                "run",
                "--mode",
                mode,
                "--execution-mode",
                execution_mode,
                "--symbol",
                symbol,
                "--source",
                resolved_source,
                "--duration",
                str(duration),
                "--async",
            ]

            proc = subprocess.Popen(cmd)
            proc.wait()

            if proc.returncode != 0:
                log_restart(
                    f"Process crashed (exit {proc.returncode}). Restarting in 10s..."
                )
            else:
                log_restart("Process exited normally. Restarting in 10s...")

            time.sleep(10)
        except KeyboardInterrupt:
            log_restart("Supervisor stopped by user.")
            break
