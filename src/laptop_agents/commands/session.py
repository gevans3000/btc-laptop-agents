import sys
import os
import time
import signal
import threading
import argparse
from laptop_agents.core.logger import logger
import typer
from pathlib import Path
from rich.console import Console
from laptop_agents.constants import REPO_ROOT, DEFAULT_SYMBOL
from laptop_agents.core.lock_manager import LockManager
from laptop_agents.core.orchestrator import LATEST_DIR
from laptop_agents.core.config import load_session_config
from laptop_agents.core.orchestrator import (
    run_orchestrated_mode,
    run_legacy_orchestration,
    append_event,
)

console = Console()
LOCK_FILE = REPO_ROOT / ".agent" / "lockfile.pid"


def run(ctx: typer.Context):
    """Wrapper for the main run logic."""

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

    lock = LockManager(LOCK_FILE)
    if not lock.acquire():
        console.print(f"[red]Already running. Check {LOCK_FILE}[/red]")
        raise typer.Exit(code=1)

    import atexit

    atexit.register(lock.release)

    ap = argparse.ArgumentParser(description="Laptop Agents CLI")
    ap.add_argument(
        "--source",
        choices=["mock", "bitunix"],
        default=os.environ.get("LA_SOURCE", "mock"),
    )
    ap.add_argument("--symbol", default=os.environ.get("LA_SYMBOL", DEFAULT_SYMBOL))
    ap.add_argument("--interval", default=os.environ.get("LA_INTERVAL", "1m"))
    ap.add_argument("--limit", type=int, default=int(os.environ.get("LA_LIMIT", "200")))
    ap.add_argument("--fees-bps", type=float, default=2.0)
    ap.add_argument("--slip-bps", type=float, default=0.5)
    ap.add_argument("--backtest", type=int, default=0)
    ap.add_argument("--backtest-mode", choices=["bar", "position"], default="position")
    ap.add_argument(
        "--mode",
        choices=[
            "single",
            "backtest",
            "live",
            "validate",
            "selftest",
            "orchestrated",
            "live-session",
        ],
        default=None,
    )
    ap.add_argument(
        "--duration", type=int, default=int(os.environ.get("LA_DURATION", "10"))
    )
    ap.add_argument("--once", action="store_true", default=False)
    ap.add_argument("--execution-mode", choices=["paper", "live"], default="paper")
    ap.add_argument("--risk-pct", type=float, default=1.0)
    ap.add_argument("--stop-bps", type=float, default=30.0)
    ap.add_argument("--tp-r", type=float, default=1.5)
    ap.add_argument("--max_leverage", type=float, default=1.0)
    ap.add_argument(
        "--intrabar-mode",
        choices=["conservative", "optimistic"],
        default="conservative",
    )
    ap.add_argument("--validate-splits", type=int, default=5)
    ap.add_argument("--validate-train", type=int, default=600)
    ap.add_argument("--validate-test", type=int, default=200)
    ap.add_argument(
        "--grid", type=str, default="sma=10,30;stop=20,30,40;tp=1.0,1.5,2.0"
    )
    ap.add_argument("--validate-max-candidates", type=int, default=200)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument(
        "--strategy", type=str, default=os.environ.get("LA_STRATEGY", "default")
    )
    ap.add_argument("--async", dest="async_mode", action="store_true", default=True)
    ap.add_argument("--sync", dest="async_mode", action="store_false")
    ap.add_argument("--stale-timeout", type=int, default=120)
    ap.add_argument("--execution-latency-ms", type=int, default=200)
    ap.add_argument("--dashboard", action="store_true")
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--replay", type=str, default=None)
    ap.add_argument("--config", type=str, default=None)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--verbose", action="store_true")

    args = ap.parse_args(ctx.args)

    if args.quiet:
        logger.setLevel("ERROR")
    elif args.verbose:
        logger.setLevel("DEBUG")

    args.symbol = args.symbol.upper().replace("/", "").replace("-", "")

    try:
        session_config = load_session_config(
            config_path=Path(args.config) if args.config else None,
            strategy_name=args.strategy,
            overrides=vars(args),
        )
    except Exception as e:
        console.print(f"[red]CONFIG ERROR: {e}[/red]")
        raise typer.Exit(code=1)

    mode = args.mode or ("backtest" if args.backtest > 0 else "single")

    append_event(
        {
            "event": "SYSTEM_STARTUP",
            "mode": mode,
            "config": session_config.model_dump(),
        },
        paper=True,
    )

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

                strat_config = session_config.model_dump()
                strat_config.update(
                    {
                        "risk": {
                            "risk_pct": args.risk_pct,
                            "stop_bps": args.stop_bps,
                            "tp_r": args.tp_r,
                            "max_leverage": args.max_leverage,
                            "equity": 10000.0,
                        },
                        "setups": {
                            "default": {"active": True, "params": {}},
                            "pullback_ribbon": {"enabled": False},
                            "sweep_invalidation": {"enabled": False},
                        },
                    }
                )

                session_result = asyncio.run(
                    run_async_session(
                        duration_min=session_config.duration,
                        symbol=session_config.symbol,
                        interval=session_config.interval,
                        starting_balance=10000.0,
                        risk_pct=args.risk_pct,
                        stop_bps=args.stop_bps,
                        tp_r=args.tp_r,
                        fees_bps=session_config.fees_bps,
                        slip_bps=session_config.slip_bps,
                        strategy_config=strat_config,
                        stale_timeout=args.stale_timeout,
                        execution_latency_ms=args.execution_latency_ms,
                        dry_run=session_config.dry_run,
                        replay_path=args.replay,
                        execution_mode=args.execution_mode,
                    )
                )
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
                dry_run=args.dry_run,
            )
            console.print(msg)
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
                validate_max_candidates=args.validate_max_candidates,
            )

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
