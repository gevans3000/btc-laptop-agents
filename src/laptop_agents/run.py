from __future__ import annotations

import argparse
import sys
import os
import atexit
import psutil
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---------------- Paths (anchor to repo root) ----------------
HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parent.parent.parent
sys.path.append(str(REPO_ROOT / "src"))

# Core Imports
from laptop_agents import __version__
from laptop_agents.core.logger import logger, setup_logger
from laptop_agents.core.orchestrator import (
    run_orchestrated_mode,
    run_legacy_orchestration,
    LATEST_DIR,
    RUNS_DIR,
)
from laptop_agents.core.logger import write_alert

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
    write_alert(f"CRITICAL: Unhandled exception: {exc_value}")

sys.excepthook = handle_exception

def run_cli(argv: list[str] = None) -> int:
    # 1.1 Single-Instance Locking
    from laptop_agents.core.lock_manager import LockManager
    LOCK_FILE = REPO_ROOT / ".agent" / "lockfile.pid"
    lock = LockManager(LOCK_FILE)
    
    if not lock.acquire():
        print(f"Already running. Check {LOCK_FILE}")
        return 1
    
    atexit.register(lock.release)

    ap = argparse.ArgumentParser(description="Laptop Agents CLI")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--source", choices=["mock", "bitunix"], default=os.environ.get("LA_SOURCE", "mock"))
    ap.add_argument("--symbol", default=os.environ.get("LA_SYMBOL", "BTCUSD"))
    ap.add_argument("--interval", default=os.environ.get("LA_INTERVAL", "1m"))
    ap.add_argument("--limit", type=int, default=int(os.environ.get("LA_LIMIT", "200")))
    ap.add_argument("--fees-bps", type=float, default=2.0)
    ap.add_argument("--slip-bps", type=float, default=0.5)
    ap.add_argument("--backtest", type=int, default=0)
    ap.add_argument("--backtest-mode", choices=["bar", "position"], default="position")
    ap.add_argument("--mode", choices=["single", "backtest", "live", "validate", "selftest", "orchestrated", "live-session"], default=None)
    ap.add_argument("--duration", type=int, default=int(os.environ.get("LA_DURATION", "10")), help="Session duration in minutes (for live-session mode)")
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
    ap.add_argument("--show", action="store_true", help="Auto-open summary.html in browser after run")
    ap.add_argument("--strategy", type=str, default=os.environ.get("LA_STRATEGY", "default"), help="Strategy name from config/strategies/")
    ap.add_argument("--async", dest="async_mode", action="store_true", default=True, help="Use high-performance asyncio engine (default)")
    ap.add_argument("--sync", dest="async_mode", action="store_false", help="Use legacy synchronous polling engine")
    ap.add_argument("--stale-timeout", type=int, default=60, help="Seconds before stale data triggers shutdown")
    ap.add_argument("--execution-latency-ms", type=int, default=200, help="Simulated network latency for order execution")
    ap.add_argument("--dashboard", action="store_true", help="Launch real-time web dashboard")
    ap.add_argument("--preflight", action="store_true", help="Run system readiness checks")
    ap.add_argument("--replay", type=str, default=None, help="Path to events.jsonl for deterministic replay")
    ap.add_argument("--config", type=str, default=None, help="Explicit path to a JSON config file")
    ap.add_argument("--quiet", action="store_true", help="Minimize terminal output")
    ap.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = ap.parse_args(argv)

    # Configure Log Level
    if args.quiet:
        logger.setLevel(logging.ERROR)
    elif args.verbose:
        logger.setLevel(logging.DEBUG)

    # Normalize symbol to uppercase
    args.symbol = args.symbol.upper().replace("/", "").replace("-", "")

    # Determine strategy
    strategy_name = args.strategy

    # Load validated configuration
    from laptop_agents.core.config import load_session_config, RunResult
    try:
        session_config = load_session_config(
            config_path=Path(args.config) if args.config else None,
            strategy_name=strategy_name,
            overrides=vars(args)
        )
        logger.info(f"Configuration validated: {session_config.model_dump_json(indent=2)}")
    except Exception as e:
        logger.error(f"CONFIG_VALIDATION_FAILED: {e}")
        return 1

    # Print Startup Banner
    if not args.quiet:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        console = Console()
        banner_table = Table.grid(padding=(0, 1))
        banner_table.add_column(style="cyan")
        banner_table.add_column(style="white")
        banner_table.add_row("Version:", f"{__version__}")
        banner_table.add_row("Symbol:", f"{session_config.symbol}")
        banner_table.add_row("Source:", f"{session_config.source}")
        banner_table.add_row("Mode:", f"{args.mode or 'auto'}")
        banner_table.add_row("Strategy:", f"{strategy_name}")
        
        console.print(Panel(banner_table, title="[bold blue]Laptop Agents Runner[/bold blue]", border_style="blue", expand=False))

    # Ensure directories exist
    RUNS_DIR.mkdir(exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)

    # Determine mode
    mode = args.mode if args.mode else ("backtest" if args.backtest > 0 else "single")

    # SYSTEM_STARTUP: Log merged configuration
    from laptop_agents.core.orchestrator import append_event
    append_event({
        "event": "SYSTEM_STARTUP",
        "mode": mode,
        "config": session_config.model_dump()
    }, paper=True)

    if args.preflight:
        from laptop_agents.core.preflight import run_preflight_checks
        success = run_preflight_checks(args)
        return 0 if success else 1

    if args.dashboard:
        from laptop_agents.dashboard.app import run_dashboard
        import threading
        dash_thread = threading.Thread(target=run_dashboard, daemon=True)
        dash_thread.start()
        logger.info("Dashboard launched at http://127.0.0.1:5000")

    try:
        ret = 1
        if mode == "live-session":
            if args.async_mode:
                import asyncio
                from laptop_agents.session.async_session import run_async_session
                # Run the async session
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
                    strategy_config=session_config.model_dump(), # Passing full config for now
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
                    strategy_config=strategy_config,
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
            print(msg)
            ret = 0 if success else 1
        else:
            ret = run_legacy_orchestration(
                mode=mode,
                symbol=args.symbol,
                interval=args.interval,
                source=args.source,
                limit=args.limit,
                fees_bps=args.fees_bps,
                slip_bps=args.slip_bps,
                risk_pct=args.risk_pct,
                stop_bps=args.stop_bps,
                tp_r=args.tp_r,
                max_leverage=args.max_leverage,
                intrabar_mode=args.intrabar_mode,
                backtest_mode=args.backtest_mode,
                validate_splits=args.validate_splits,
                validate_train=args.validate_train,
                validate_test=args.validate_test,
                grid_str=args.grid,
                validate_max_candidates=args.validate_max_candidates
            )

        # Post-Run Validation & Summary
        summary_path = LATEST_DIR / "summary.html"
        events_path = LATEST_DIR / "events.jsonl"
        
        if not args.quiet:
            from rich.console import Console
            from rich.table import Table
            console = Console()
            console.print("\n[bold green]Session Summary[/bold green]")
            summary_table = Table(show_header=False, box=None)
            summary_table.add_row("Duration:", f"{args.duration}m")
            summary_table.add_row("Artifacts:", f"{LATEST_DIR}")
            summary_table.add_row("Summary:", "Found" if summary_path.exists() else "[red]Missing[/red]")
            summary_table.add_row("Events:", "Found" if events_path.exists() else "[red]Missing[/red]")
            console.print(summary_table)

        # Final exit code logic
        if not summary_path.exists() or not events_path.exists():
            logger.error(f"Missing essential artifacts in {LATEST_DIR}")
            return 1

        # Auto-open summary if requested
        if args.show:
            import webbrowser
            if summary_path.exists():
                webbrowser.open(f"file:///{summary_path.resolve()}")

        return ret
    except Exception as e:
        logger.exception(f"CLI wrapper failed: {e}")
        from laptop_agents.core.logger import write_alert
        write_alert(f"CRITICAL: CLI wrapper failed - {e}")
        return 1

if __name__ == "__main__":
    sys.exit(run_cli())
