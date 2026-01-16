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

import subprocess
import psutil
import signal
import threading
import argparse
import logging
from dotenv import load_dotenv

load_dotenv()

app = typer.Typer(help="Laptop Agents Unified CLI")
console = Console()

AGENT_PID_FILE = REPO_ROOT / ".workspace" / "agent.pid"
LOGS_DIR = REPO_ROOT / ".workspace" / "logs"

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    # This assumes 'logger' and 'write_alert' are available
    from laptop_agents.core.logger import logger, write_alert
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
    write_alert(f"CRITICAL: Unhandled exception: {exc_value}")

sys.excepthook = handle_exception

@app.command(help="Start a trading session (supports background execution)")
def start(
    mode: str = typer.Option("live-session", help="Mode: live-session, backtest, etc."),
    execution_mode: str = typer.Option("paper", help="paper or live"),
    symbol: str = typer.Option("BTCUSD", help="Symbol to trade"),
    detach: bool = typer.Option(False, "--detach", help="Run in background"),
):
    """Launch a session and manage PID."""
    if AGENT_PID_FILE.exists():
        try:
            old_pid = int(AGENT_PID_FILE.read_text().strip())
            if psutil.pid_exists(old_pid):
                console.print(f"[red]Error: Agent already running (PID: {old_pid})[/red]")
                return
        except Exception:
            pass

    cmd = [
        sys.executable,
        "-m", "laptop_agents", "run",
        "--mode", mode,
        "--execution-mode", execution_mode,
        "--symbol", symbol,
        "--async"
    ]

    if detach:
        console.print(f"[green]Starting agent in background (mode={mode}, {execution_mode})...[/green]")
        # Use subprocess.Popen with detached flags
        if sys.platform == "win32":
            proc = subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                cwd=str(REPO_ROOT)
            )
        else:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                cwd=str(REPO_ROOT)
            )
        AGENT_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        AGENT_PID_FILE.write_text(str(proc.pid))
        console.print(f"[bold green]Agent started with PID: {proc.pid}[/bold green]")
    else:
        # Run in foreground
        try:
            AGENT_PID_FILE.parent.mkdir(parents=True, exist_ok=True)
            # We can't really write OUR pid because we are the parent,
            # but we want to track the CHILD's pid.
            proc = subprocess.Popen(cmd, cwd=str(REPO_ROOT))
            AGENT_PID_FILE.write_text(str(proc.pid))
            proc.wait()
        finally:
            if AGENT_PID_FILE.exists():
                AGENT_PID_FILE.unlink()

@app.command(help="Stop any running trading session")
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

    # Backup: search for run.py processes
    console.print("[yellow]PID file missing or invalid. Searching for run.py processes...[/yellow]")
    found = False
    for p in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = p.info.get('cmdline')
            if cmdline and any("run.py" in arg for arg in cmdline) and any("python" in arg.lower() for arg in cmdline):
                console.print(f"Killing process {p.info['pid']}...")
                p.terminate()
                found = True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    if found:
        console.print("[green]Processes stopped.[/green]")
    else:
        console.print("[red]No running agent found.[/red]")

@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
    help="Run a trading session (passes all arguments to the runner logic)"
)
def run(ctx: typer.Context):
    """Wrapper for the main run logic."""
    # Move the run_cli logic here or call a local version
    from laptop_agents.core.logger import logger
    
    def signal_handler(sig, frame):
        console.print("\n[bold red]!!! SHUTTING DOWN !!![/bold red]")
        logger.info("Signal received, initiating graceful shutdown...")
        
        def force_exit():
            time.sleep(3)
            console.print("[red]Shutdown stuck. Forced exit.[/red]")
            os._exit(0)
        
        threading.Thread(target=force_exit, daemon=True).start()
        logger.info("Clean shutdown triggered. Closing positions...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    from laptop_agents.core.lock_manager import LockManager
    LOCK_FILE = REPO_ROOT / ".agent" / "lockfile.pid"
    lock = LockManager(LOCK_FILE)
    
    if not lock.acquire():
        console.print(f"[red]Already running. Check {LOCK_FILE}[/red]")
        raise typer.Exit(code=1)
    
    import atexit
    atexit.register(lock.release)

    # Re-use the argument parsing logic from the old run.py
    # but adjust for Typer's ctx.args
    ap = argparse.ArgumentParser(description="Laptop Agents CLI")
    ap.add_argument("--source", choices=["mock", "bitunix"], default=os.environ.get("LA_SOURCE", "mock"))
    ap.add_argument("--symbol", default=os.environ.get("LA_SYMBOL", "BTCUSD"))
    ap.add_argument("--interval", default=os.environ.get("LA_INTERVAL", "1m"))
    ap.add_argument("--limit", type=int, default=int(os.environ.get("LA_LIMIT", "200")))
    ap.add_argument("--fees-bps", type=float, default=2.0)
    ap.add_argument("--slip-bps", type=float, default=0.5)
    ap.add_argument("--backtest", type=int, default=0)
    ap.add_argument("--backtest-mode", choices=["bar", "position"], default="position")
    ap.add_argument("--mode", choices=["single", "backtest", "live", "validate", "selftest", "orchestrated", "live-session"], default=None)
    ap.add_argument("--duration", type=int, default=int(os.environ.get("LA_DURATION", "10")))
    ap.add_argument("--once", action="store_true", default=False)
    ap.add_argument("--execution-mode", choices=["paper", "live"], default="paper")
    ap.add_argument("--risk-pct", type=float, default=1.0)
    ap.add_argument("--stop-bps", type=float, default=30.0)
    ap.add_argument("--tp-r", type=float, default=1.5)
    ap.add_argument("--max_leverage", type=float, default=1.0)
    ap.add_argument("--intrabar-mode", choices=["conservative", "optimistic"], default="conservative")
    ap.add_argument("--validate-splits", type=int, default=5)
    ap.add_argument("--validate-train", type=int, default=600)
    ap.add_argument("--validate-test", type=int, default=200)
    ap.add_argument("--grid", type=str, default="sma=10,30;stop=20,30,40;tp=1.0,1.5,2.0")
    ap.add_argument("--validate-max-candidates", type=int, default=200)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--strategy", type=str, default=os.environ.get("LA_STRATEGY", "default"))
    ap.add_argument("--async", dest="async_mode", action="store_true", default=True)
    ap.add_argument("--sync", dest="async_mode", action="store_false")
    ap.add_argument("--stale-timeout", type=int, default=60)
    ap.add_argument("--execution-latency-ms", type=int, default=200)
    ap.add_argument("--dashboard", action="store_true")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--replay", type=str, default=None)
    ap.add_argument("--config", type=str, default=None)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    
    args = ap.parse_args(ctx.args)

    # Core Execution Logic (imported from respective modules)
    from laptop_agents.core.config import load_session_config
    if args.quiet: logger.setLevel(logging.ERROR)
    elif args.verbose: logger.setLevel(logging.DEBUG)
    
    args.symbol = args.symbol.upper().replace("/", "").replace("-", "")
    
    try:
        session_config = load_session_config(
            config_path=Path(args.config) if args.config else None,
            strategy_name=args.strategy,
            overrides=vars(args)
        )
    except Exception as e:
        console.print(f"[red]CONFIG ERROR: {e}[/red]")
        raise typer.Exit(code=1)

    # ... and so on for the rest of the logic from run.py
    # To keep this manageable, I'll import the execution parts 
    # but keep the structure in main.py.
    from laptop_agents.core.orchestrator import (
        run_orchestrated_mode,
        run_legacy_orchestration,
        append_event
    )

    mode = args.mode or ("backtest" if args.backtest > 0 else "single")

    append_event({
        "event": "SYSTEM_STARTUP",
        "mode": mode,
        "config": session_config.model_dump()
    }, paper=True)

    if args.preflight:
        from laptop_agents.core.preflight import run_preflight_checks
        success = run_preflight_checks(args)
        raise typer.Exit(code=0 if success else 1)

    if args.dashboard:
        from laptop_agents.dashboard.app import run_dashboard
        dash_thread = threading.Thread(target=run_dashboard, daemon=True)
        dash_thread.start()
        logger.info("Dashboard launched at http://127.0.0.1:5000")

    try:
        ret = 1
        if mode == "live-session":
            if args.async_mode:
                import asyncio
                from laptop_agents.session.async_session import run_async_session
                session_result = asyncio.run(run_async_session(
                    duration_min=session_config.duration,
                    symbol=session_config.symbol,
                    interval=session_config.interval,
                    starting_balance=10000.0,
                    risk_pct=args.risk_pct,
                    stop_bps=args.stop_bps,
                    tp_r=args.tp_r,
                    fees_bps=session_config.fees_bps,
                    slip_bps=session_config.slip_bps,
                    strategy_config=session_config.model_dump(),
                    stale_timeout=args.stale_timeout,
                    execution_latency_ms=args.execution_latency_ms,
                    dry_run=session_config.dry_run,
                    replay_path=args.replay,
                ))
                ret = 0 if session_result.errors == 0 else 1
            else:
                from laptop_agents.session.timed_session import run_timed_session
                result = run_timed_session(
                    duration_min=args.duration,
                    poll_interval_sec=60,
                    symbol=args.symbol,
                    interval=args.interval,
                    source=args.source,
                    limit=args.limit,
                    starting_balance=10000.0,
                    risk_pct=args.risk_pct,
                    stop_bps=args.stop_bps,
                    tp_r=args.tp_r,
                    execution_mode=args.execution_mode,
                    fees_bps=args.fees_bps,
                    slip_bps=args.slip_bps,
                    strategy_config=session_config.model_dump(),
                )
                ret = 0 if result.errors == 0 else 1
        elif mode == "orchestrated":
            success, msg = run_orchestrated_mode(
                symbol=args.symbol,
                interval=args.interval,
                source=args.source,
                limit=args.limit,
                fees_bps=args.fees_bps,
                slip_bps=args.slip_bps,
                risk_pct=args.risk_pct,
                stop_bps=args.stop_bps,
                tp_r=args.tp_r,
                execution_mode=args.execution_mode,
                dry_run=args.dry_run
            )
            console.print(msg)
            ret = 0 if success else 1
        else:
            ret = run_legacy_orchestration(
                mode=mode, symbol=args.symbol, interval=args.interval,
                source=args.source, limit=args.limit, fees_bps=args.fees_bps,
                slip_bps=args.slip_bps, risk_pct=args.risk_pct, stop_bps=args.stop_bps,
                tp_r=args.tp_r, max_leverage=args.max_leverage,
                intrabar_mode=args.intrabar_mode, backtest_mode=args.backtest_mode,
                validate_splits=args.validate_splits, validate_train=args.validate_train,
                validate_test=args.validate_test, grid_str=args.grid,
                validate_max_candidates=args.validate_max_candidates
            )

        # Artifact validation (skip for selftest which doesn't generate artifacts)
        if mode != "selftest":
            summary_path = LATEST_DIR / "summary.html"
            if not summary_path.exists():
                logger.error(f"Missing essential artifacts in {LATEST_DIR}")
                ret = 1
                
            if args.show and summary_path.exists():
                import webbrowser
                webbrowser.open(f"file:///{summary_path.resolve()}")

        raise typer.Exit(code=ret)
    except Exception as e:
        if not isinstance(e, typer.Exit):
            logger.exception(f"Run failed: {e}")
        raise

@app.command(help="Watch and supervisor an agent session (auto-restart on crash)")
def watch(
    mode: str = typer.Option("live-session", help="Mode: live-session, backtest, etc."),
    execution_mode: str = typer.Option("paper", help="paper or live"),
    symbol: str = typer.Option("BTCUSD", help="Symbol to trade"),
    duration: int = typer.Option(10, help="Duration in minutes"),
):
    """Monitor a session; if it exits with a non-zero code, wait 10s and restart."""
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
                "-m", "laptop_agents", "run",
                "--mode", mode,
                "--execution-mode", execution_mode,
                "--symbol", symbol,
                "--duration", str(duration),
                "--async"
            ]
            
            proc = subprocess.Popen(cmd)
            proc.wait()
            
            if proc.returncode != 0:
                log_restart(f"Process crashed (exit {proc.returncode}). Restarting in 10s...")
            else:
                log_restart("Process exited normally. Restarting in 10s...")
            
            time.sleep(10)
        except KeyboardInterrupt:
            log_restart("Supervisor stopped by user.")
            break

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
def doctor(fix: bool = typer.Option(False, "--fix", help="Attempt to fix missing directories and environment")):
    """Verify system readiness and environment."""
    console.print("[bold blue]Laptop Agents Doctor[/bold blue]\n")
    
    if fix:
        # Create .workspace/ structure
        workspace_dir = REPO_ROOT / ".workspace"
        for sub in ["runs", "logs", "paper"]:
            (workspace_dir / sub).mkdir(parents=True, exist_ok=True)
        console.print("[green]✓ Verified .workspace/ structure.[/green]")
        
        # Copy .env.example to .env if missing
        env_path = REPO_ROOT / ".env"
        env_example = REPO_ROOT / ".env.example"
        if not env_path.exists() and env_example.exists():
            import shutil
            shutil.copy2(env_example, env_path)
            console.print("[yellow]! Created .env from .env.example. PLEASE EDIT IT.[/yellow]")
            
    # Bitunix API Key check
    bitunix_status = "OK"
    live_mode = os.environ.get("LA_EXECUTION_MODE") == "live" or os.environ.get("LA_SOURCE") == "bitunix"
    if live_mode:
        api_key = os.environ.get("BITUNIX_API_KEY")
        api_secret = os.environ.get("BITUNIX_API_SECRET")
        if not api_key or not api_secret:
            bitunix_status = "MISSING"
    
    checks = [
        ("Python Version", sys.version.split()[0], ">=3.10"),
        ("Repo Root", str(REPO_ROOT), "exists"),
        (".env file", "exists" if (REPO_ROOT / ".env").exists() else "MISSING", "required"),
        ("Config Dir", "exists" if (REPO_ROOT / "config").exists() else "MISSING", "required"),
        ("Workspace", "exists" if (REPO_ROOT / ".workspace").exists() else "MISSING", "required"),
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
        elif label == "Bitunix Keys" and val == "MISSING":
             result = "[red]FAIL[/red]"
        else:
            result = "[green]PASS[/green]"
        table.add_row(label, str(val), exp, result)
        
    console.print(table)
    
    if not fix and any(c[1] == "MISSING" for c in checks):
        console.print("\n[yellow]Hint: Run 'la doctor --fix' to automate setup.[/yellow]")

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
