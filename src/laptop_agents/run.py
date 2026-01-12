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
    ap.add_argument("--source", choices=["mock", "bitunix"], default="mock")
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
    args = ap.parse_args()

    # Ensure directories exist
    RUNS_DIR.mkdir(exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)

    # Determine mode
    mode = args.mode if args.mode else ("backtest" if args.backtest > 0 else "single")

    try:
        if mode == "live-session":
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
            )
            return 0 if result.errors == 0 else 1
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
            return 0 if success else 1
        else:
            return run_legacy_orchestration(
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

    except Exception as e:
        logger.exception(f"CLI wrapper failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
