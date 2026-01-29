import sys
import os
import time
import signal
import threading
from types import SimpleNamespace
from laptop_agents.core.logger import logger
import typer
from pathlib import Path
from rich.console import Console
from laptop_agents.constants import AGENT_PID_FILE, DEFAULT_SYMBOL
from laptop_agents.core.lock_manager import LockManager
from laptop_agents.core.orchestrator import LATEST_DIR
from laptop_agents.core.config import load_session_config, load_strategy_config
from laptop_agents.core.orchestrator import (
    run_orchestrated_mode,
    append_event,
)

console = Console()
LOCK_FILE = AGENT_PID_FILE


def _start_dashboard(port: int = 5000):
    try:
        from laptop_agents.dashboard.app import run_dashboard
    except ImportError:
        from rich.console import Console

        Console().print(
            "[red]Dashboard requires Flask. Install with: pip install btc-laptop-agents[dashboard][/red]"
        )
        raise SystemExit(1)
    run_dashboard(port)


def run(
    source: str = typer.Option(
        os.environ.get("LA_SOURCE", "mock"),
        "--source",
        help="Data source (mock or bitunix).",
    ),
    symbol: str = typer.Option(
        os.environ.get("LA_SYMBOL", DEFAULT_SYMBOL),
        "--symbol",
        help="Trading symbol (default BTCUSDT).",
    ),
    interval: str = typer.Option(
        os.environ.get("LA_INTERVAL", "1m"),
        "--interval",
        help="Candle interval.",
    ),
    limit: int = typer.Option(
        int(os.environ.get("LA_LIMIT", "200")),
        "--limit",
        help="Candle fetch limit.",
    ),
    fees_bps: float = typer.Option(2.0, "--fees-bps", help="Fees in bps."),
    slip_bps: float = typer.Option(0.5, "--slip-bps", help="Slippage in bps."),
    backtest: int = typer.Option(0, "--backtest", help="Backtest length in days."),
    backtest_mode: str = typer.Option(
        "position",
        "--backtest-mode",
        help="Backtest mode (bar or position).",
    ),
    mode: str | None = typer.Option(
        None,
        "--mode",
        help="Execution mode (single/backtest/live/validate/selftest/orchestrated/live-session).",
    ),
    duration: int = typer.Option(
        int(os.environ.get("LA_DURATION", "10")),
        "--duration",
        help="Session duration in minutes.",
    ),
    once: bool = typer.Option(False, "--once", help="Run a single cycle and exit."),
    execution_mode: str = typer.Option(
        "paper", "--execution-mode", help="Execution mode (paper or live)."
    ),
    risk_pct: float = typer.Option(1.0, "--risk-pct", help="Risk percentage."),
    stop_bps: float = typer.Option(30.0, "--stop-bps", help="Stop loss in bps."),
    tp_r: float = typer.Option(1.5, "--tp-r", help="Take profit R multiple."),
    max_leverage: float = typer.Option(1.0, "--max-leverage", help="Max leverage."),
    intrabar_mode: str = typer.Option(
        "conservative",
        "--intrabar-mode",
        help="Intrabar mode (conservative or optimistic).",
    ),
    validate_splits: int = typer.Option(5, "--validate-splits"),
    validate_train: int = typer.Option(600, "--validate-train"),
    validate_test: int = typer.Option(200, "--validate-test"),
    grid: str = typer.Option(
        "sma=10,30;stop=20,30,40;tp=1.0,1.5,2.0",
        "--grid",
        help="Validation grid definition.",
    ),
    validate_max_candidates: int = typer.Option(200, "--validate-max-candidates"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Dry run (no trades)."),
    show: bool = typer.Option(False, "--show", help="Open summary after run."),
    strategy: str = typer.Option(
        os.environ.get("LA_STRATEGY", "default"),
        "--strategy",
        help="Strategy name.",
    ),
    async_mode: bool = typer.Option(
        True,
        "--async/--sync",
        help="Use async session runner.",
    ),
    stale_timeout: int = typer.Option(120, "--stale-timeout"),
    execution_latency_ms: int = typer.Option(200, "--execution-latency-ms"),
    dashboard: bool = typer.Option(False, "--dashboard", help="Launch dashboard."),
    preflight: bool = typer.Option(False, "--preflight", help="Run preflight checks."),
    replay: str | None = typer.Option(None, "--replay", help="Replay path."),
    config: str | None = typer.Option(None, "--config", help="Config file path."),
    quiet: bool = typer.Option(False, "--quiet", help="Silence logs."),
    verbose: bool = typer.Option(False, "--verbose", help="Verbose logs."),
    profile: str = typer.Option(
        "paper", "--profile", help="Config profile: backtest, paper, live."
    ),
):
    """Wrapper for the main run logic."""

    lock = LockManager(LOCK_FILE)
    if not lock.acquire():
        console.print(f"[red]Already running. Check {LOCK_FILE}[/red]")
        raise typer.Exit(code=1)

    import atexit

    atexit.register(lock.release)

    args = SimpleNamespace(
        source=source,
        symbol=symbol,
        interval=interval,
        limit=limit,
        fees_bps=fees_bps,
        slip_bps=slip_bps,
        backtest=backtest,
        backtest_mode=backtest_mode,
        mode=mode,
        duration=duration,
        once=once,
        execution_mode=execution_mode,
        risk_pct=risk_pct,
        stop_bps=stop_bps,
        tp_r=tp_r,
        max_leverage=max_leverage,
        intrabar_mode=intrabar_mode,
        validate_splits=validate_splits,
        validate_train=validate_train,
        validate_test=validate_test,
        grid=grid,
        validate_max_candidates=validate_max_candidates,
        dry_run=dry_run,
        show=show,
        strategy=strategy,
        async_mode=async_mode,
        stale_timeout=stale_timeout,
        execution_latency_ms=execution_latency_ms,
        dashboard=dashboard,
        preflight=preflight,
        replay=replay,
        config=config,
        quiet=quiet,
        verbose=verbose,
    )

    def signal_handler(sig, frame):
        console.print("\n[bold red]!!! SHUTTING DOWN !!![/bold red]")
        logger.info("Signal received, initiating graceful shutdown...")
        if args.mode == "live-session" and args.async_mode:
            os.environ["LA_KILL_SWITCH"] = "TRUE"
            logger.info("Async session kill switch set; waiting for graceful shutdown.")
            return

        def force_exit():
            time.sleep(3)
            console.print("[red]Shutdown stuck. Forced exit.[/red]")
            os._exit(0)

        threading.Thread(target=force_exit, daemon=True).start()
        logger.info("Clean shutdown triggered. Closing positions...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if args.quiet:
        logger.setLevel("ERROR")
    elif args.verbose:
        logger.setLevel("DEBUG")

    args.symbol = args.symbol.upper().replace("/", "").replace("-", "")

    from laptop_agents.core.config_loader import load_profile

    profile_config = load_profile(profile, cli_overrides=vars(args))

    try:
        session_config = load_session_config(
            config_path=Path(args.config) if args.config else None,
            strategy_name=args.strategy,
            overrides=vars(args),
        )
    except Exception as e:
        console.print(f"[red]CONFIG ERROR: {e}[/red]")
        raise typer.Exit(code=1)

    mode = (
        args.mode
        or profile_config.get("mode")
        or ("backtest" if args.backtest > 0 else "single")
    )

    append_event(
        {
            "event": "SYSTEM_STARTUP",
            "mode": mode,
            "config": session_config.model_dump(),
        },
        paper=True,
    )

    if args.preflight or profile == "live":
        from laptop_agents.core.preflight import run_preflight, all_gates_passed
        from rich.table import Table

        results = run_preflight(profile_config)

        table = Table(title="Live Trading Preflight")
        table.add_column("Gate", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Message", style="dim")

        for r in results:
            status = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
            table.add_row(r.name, status, r.message)

        console.print(table)

        if not all_gates_passed(results):
            console.print(
                "[red bold]FATAL: Preflight failed. Live mode blocked.[/red bold]"
            )
            raise typer.Exit(code=1)

        if args.preflight and profile != "live":
            raise typer.Exit(code=0)

    if args.dashboard:
        dash_thread = threading.Thread(target=_start_dashboard, daemon=True)
        dash_thread.start()
        logger.info("Dashboard launched at http://127.0.0.1:5000")

    try:
        ret = 1
        if mode == "live-session":
            if args.async_mode:
                import asyncio
                from laptop_agents.session.async_session import run_async_session

                # Strategy config is distinct from SessionConfig; preserve documented precedence
                # (CLI overrides > config/strategies/<name>.json > built-in defaults).
                strat_config = load_strategy_config(
                    args.strategy,
                    overrides={
                        "risk": {"risk_pct": args.risk_pct},
                        "source": session_config.source,
                    },
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
        elif mode == "selftest":
            console.print("Running selftest...")
            success, msg = run_orchestrated_mode(
                symbol="BTCUSDT",
                interval="1m",
                source="mock",
                limit=100,
                fees_bps=2.0,
                slip_bps=0.5,
                risk_pct=1.0,
                stop_bps=30.0,
                tp_r=1.5,
                execution_mode="paper",
                dry_run=True,
            )
            if success:
                console.print("SELFTEST PASS")
                ret = 0
            else:
                console.print(f"SELFTEST FAIL: {msg}")
                ret = 1
        elif mode == "paper":
            # Paper mode: Run orchestrated with paper execution
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
                execution_mode="paper",
                dry_run=args.dry_run,
            )
            console.print(msg)
            ret = 0 if success else 1
        else:
            console.print(
                f"[red]Unknown mode: {mode}. Defaulting to orchestrated...[/red]"
            )
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
