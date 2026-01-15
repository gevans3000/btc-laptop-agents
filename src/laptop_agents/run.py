from __future__ import annotations

import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ---------------- Paths (anchor to repo root) ----------------
HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parent.parent.parent
sys.path.append(str(REPO_ROOT / "src"))

# Core Imports
from laptop_agents.core.logger import logger
from laptop_agents.core.orchestrator import (
    run_orchestrated_mode,
    run_legacy_orchestration,
    LATEST_DIR,
    RUNS_DIR,
)

def main() -> int:
    ap = argparse.ArgumentParser(description="Laptop Agents CLI")
    ap.add_argument("--source", choices=["mock", "bitunix"], default="bitunix")
    ap.add_argument("--symbol", default="BTCUSD")
    ap.add_argument("--interval", default="1m")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--fees-bps", type=float, default=2.0)
    ap.add_argument("--slip-bps", type=float, default=0.5)
    ap.add_argument("--backtest", type=int, default=0)
    ap.add_argument("--backtest-mode", choices=["bar", "position"], default="position")
    ap.add_argument("--mode", choices=["single", "backtest", "live", "validate", "selftest", "orchestrated", "live-session"], default=None)
    ap.add_argument("--duration", type=int, default=10, help="Session duration in minutes (for live-session mode)")
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
    ap.add_argument("--strategy", type=str, default="default", help="Strategy name from config/strategies/")
    ap.add_argument("--async", dest="async_mode", action="store_true", default=True, help="Use high-performance asyncio engine (default)")
    ap.add_argument("--sync", dest="async_mode", action="store_false", help="Use legacy synchronous polling engine")
    ap.add_argument("--stale-timeout", type=int, default=60, help="Seconds before stale data triggers shutdown")
    ap.add_argument("--preflight", action="store_true", help="Run system readiness checks")
    ap.add_argument("--replay", type=str, default=None, help="Path to events.jsonl for deterministic replay")
    args = ap.parse_args()

    # Normalize symbol to uppercase
    args.symbol = args.symbol.upper().replace("/", "").replace("-", "")

    # Load strategy configuration
    import json
    strategy_path = REPO_ROOT / "config" / "strategies" / f"{args.strategy}.json"
    fallback_path = REPO_ROOT / "config" / "default.json"
    
    if strategy_path.exists():
        with open(strategy_path) as f:
            strategy_config = json.load(f)
        logger.info(f"Loaded strategy: {args.strategy}")
    elif fallback_path.exists():
        with open(fallback_path) as f:
            strategy_config = json.load(f)
        logger.warning(f"Strategy '{args.strategy}' not found, using default.json")
    else:
        strategy_config = {}
        logger.warning("No strategy config found, using CLI defaults")

    # Override CLI defaults from strategy config
    risk_cfg = strategy_config.get("risk", {})
    if "risk_pct" in risk_cfg and args.risk_pct == 1.0:
        args.risk_pct = risk_cfg["risk_pct"]
    if "rr_min" in risk_cfg and args.tp_r == 1.5:
        args.tp_r = risk_cfg["rr_min"]

    # Validate Configuration
    from laptop_agents.core.validation import validate_config
    validate_config(args, strategy_config)

    # Ensure directories exist
    RUNS_DIR.mkdir(exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)

    # Determine mode
    mode = args.mode if args.mode else ("backtest" if args.backtest > 0 else "single")

    if args.preflight:
        from laptop_agents.core.preflight import run_preflight_checks
        success = run_preflight_checks(args)
        return 0 if success else 1

    try:
        ret = 1
        if mode == "live-session":
            if args.async_mode:
                import asyncio
                from laptop_agents.session.async_session import run_async_session
                # Run the async session
                result = asyncio.run(run_async_session(
                    duration_min=args.duration,
                    symbol=args.symbol,
                    interval=args.interval,
                    starting_balance=10000.0,
                    risk_pct=args.risk_pct,
                    stop_bps=args.stop_bps,
                    tp_r=args.tp_r,
                    fees_bps=args.fees_bps,
                    slip_bps=args.slip_bps,
                    strategy_config=strategy_config,
                    stale_timeout=args.stale_timeout,
                    replay_path=args.replay,
                ))
                ret = 0 if result.errors == 0 else 1
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

        # Auto-open summary if requested
        if args.show:
            import webbrowser
            summary_path = LATEST_DIR / "summary.html"
            if summary_path.exists():
                webbrowser.open(f"file:///{summary_path.resolve()}")

        return ret
    except Exception as e:
        logger.exception(f"CLI wrapper failed: {e}")
        from laptop_agents.core.logger import write_alert
        write_alert(f"CRITICAL: CLI wrapper failed - {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
