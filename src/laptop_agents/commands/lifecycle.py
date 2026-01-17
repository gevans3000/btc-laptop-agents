import sys
import time
import subprocess
import psutil
import typer
from rich.console import Console
from laptop_agents.constants import REPO_ROOT, DEFAULT_SYMBOL

console = Console()
AGENT_PID_FILE = REPO_ROOT / ".workspace" / "agent.pid"


def start(
    mode: str = typer.Option("live-session", help="Mode: live-session, backtest, etc."),
    execution_mode: str = typer.Option("paper", help="paper or live"),
    symbol: str = typer.Option(DEFAULT_SYMBOL, help="Symbol to trade"),
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
    """Kill running session using PID file or process search."""
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

    console.print(
        "[yellow]PID file missing or invalid. Searching for run.py processes...[/yellow]"
    )
    found = False
    for p in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = p.info.get("cmdline")
            if (
                cmdline
                and any("run.py" in arg for arg in cmdline)
                and any("python" in arg.lower() for arg in cmdline)
            ):
                console.print(f"Killing process {p.info['pid']}...")
                p.terminate()
                found = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if found:
        console.print("[green]Processes stopped.[/green]")
    else:
        console.print("[red]No running agent found.[/red]")


def watch(
    mode: str = typer.Option("live-session", help="Mode: live-session, backtest, etc."),
    execution_mode: str = typer.Option("paper", help="paper or live"),
    symbol: str = typer.Option(DEFAULT_SYMBOL, help="Symbol to trade"),
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

    log_restart(f"Supervisor started for {symbol} ({mode}, {execution_mode})")

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
