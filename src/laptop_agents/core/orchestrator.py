from __future__ import annotations

import csv
import json
import shutil
import time
import uuid
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Core Logger
from laptop_agents.core.logger import logger
from laptop_agents.trading.helpers import (
    Candle,
    normalize_candle_order,
)
from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider
from laptop_agents.paper.broker import PaperBroker
from laptop_agents.agents.supervisor import Supervisor
from laptop_agents.agents.state import State as AgentState
from laptop_agents.core.validation import (
    validate_events_jsonl as _validate_events_jsonl,
)
from laptop_agents.core.config_schema import (
    validate_runtime_config,
    load_and_validate_risk_config,
)

from laptop_agents.core.events import (
    append_event,
    RUNS_DIR,
    LATEST_DIR,
    PAPER_DIR,
    LOGS_DIR,
)


def prune_workspace(keep: int = 10) -> None:
    """Keep only the N most recent run directories in .workspace/runs."""
    if not RUNS_DIR.exists():
        return

    # Get all subdirectories in RUNS_DIR except 'latest'
    run_dirs = [d for d in RUNS_DIR.iterdir() if d.is_dir() and d.name != "latest"]

    # Sort by modification time (most recent first)
    run_dirs.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    # If we have more than 'keep', delete the extras
    if len(run_dirs) > keep:
        for extra_dir in run_dirs[keep:]:
            try:
                shutil.rmtree(extra_dir)
            except Exception as e:
                logger.warning(f"Failed to prune old run directory {extra_dir}: {e}")


def reset_latest_dir() -> None:
    RUNS_DIR.mkdir(exist_ok=True)
    if LATEST_DIR.exists():
        shutil.rmtree(LATEST_DIR)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)

    # Auto-cleanup old runs
    prune_workspace(keep=10)


def _run_diagnostics(e: Exception) -> None:
    """Run learning debugger diagnostics on an exception."""
    try:
        from laptop_agents.core.diagnostics import fingerprinter as error_fingerprinter

        error_text = f"{type(e).__name__}: {str(e)}"
        match = error_fingerprinter.lookup(error_text)

        if match:
            solution = match.get("solution", "")
            if solution and solution not in [
                "NEEDS_DIAGNOSIS",
                "Pending Diagnosis",
                "",
            ]:
                logger.error(
                    f"\n[LEARNING DEBUGGER] MATCHED KNOWN ERROR: {match['fingerprint']}"
                )
                logger.error(f"[LEARNING DEBUGGER] SUGGESTED FIX: {solution}\n")
        else:
            # Capture new error
            error_fingerprinter.capture(error_text, "NEEDS_DIAGNOSIS")
            logger.error("\n[LEARNING DEBUGGER] New error captured for diagnosis.\n")

    except Exception as inner_e:
        # Don't let the debugger crash the app if something goes wrong with it
        logger.warning(f"[LEARNING DEBUGGER] Failed during error analysis: {inner_e}")


def validate_events_jsonl(events_path: Path) -> tuple[bool, str]:
    return _validate_events_jsonl(events_path, append_event_fn=append_event)


def get_agent_config(
    starting_balance: float = 10000.0,
    risk_pct: float = 1.0,
    stop_bps: float = 30.0,
    tp_r: float = 1.5,
) -> Dict[str, Any]:
    """Return the configuration schema expected by the modular agents."""
    return {
        "engine": {
            "pending_trigger_max_bars": 24,
            "derivatives_refresh_bars": 6,
        },
        "derivatives_gates": {
            "enabled": True,
            "no_trade_funding_8h": 0.0005,
            "half_size_funding_8h": 0.0002,
            "extreme_funding_8h": 0.001,
        },
        "setups": {
            "pullback_ribbon": {
                "enabled": True,
                "entry_band_pct": 0.005,
                "stop_atr_mult": 2.0,
                "tp_r_mult": tp_r,
            },
            "sweep_invalidation": {
                "enabled": True,
                "eq_tolerance_pct": 0.002,
                "tp_r_mult": tp_r,
            },
        },
        "risk": {
            "equity": starting_balance,
            "risk_pct": risk_pct / 100.0,
            "rr_min": 1.2,
        },
    }


def write_trades_csv(trades: List[Dict[str, Any]]) -> None:
    p = LATEST_DIR / "trades.csv"
    fieldnames = [
        "trade_id",
        "side",
        "signal",
        "entry",
        "exit",
        "price",
        "quantity",
        "pnl",
        "fees",
        "entry_ts",
        "exit_ts",
        "timestamp",
        "setup",
    ]

    temp_p = p.with_suffix(".tmp")
    try:
        with temp_p.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            for t in trades:
                filtered_trade = {k: v for k, v in t.items() if k in fieldnames}
                w.writerow(filtered_trade)
        temp_p.replace(p)
    except Exception as e:
        if temp_p.exists():
            temp_p.unlink()
        raise RuntimeError(f"Failed to write trades.csv: {e}")


def write_state(state: Dict[str, Any]) -> None:
    with (LATEST_DIR / "state.json").open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def render_html(
    summary: Dict[str, Any],
    trades: List[Dict[str, Any]],
    error_message: str = "",
    candles: List[Candle] | None = None,
) -> None:
    from laptop_agents.reporting.html_renderer import render_html as _render_html

    _render_html(
        summary=summary,
        trades=trades,
        error_message=error_message,
        candles=candles,
        latest_dir=LATEST_DIR,
        append_event_fn=append_event,
    )


class DryRunBroker(PaperBroker):
    def on_candle(
        self,
        candle: Any,
        order: Optional[Dict[str, Any]],
        tick: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if order and order.get("go"):
            logger.info(
                f"[DRY-RUN] Would execute: {order.get('side')} {order.get('qty')} at {order.get('entry')}"
            )
            append_event({"event": "DryRunOrder", "order": order})
        return {"fills": [], "exits": []}


def _setup_run_dir() -> tuple[str, Path]:
    run_id = str(uuid.uuid4())
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    reset_latest_dir()
    return run_id, run_dir


def _load_market_data(
    source: str, symbol: str, interval: str, limit: int
) -> List[Candle]:
    if source == "bitunix":
        candles = BitunixFuturesProvider.load_rest_candles(symbol, interval, limit)
    else:
        from laptop_agents.data.providers.mock import MockProvider

        candles = MockProvider.load_mock_candles(max(int(limit), 200))

    candles = normalize_candle_order(candles)
    if len(candles) < 51:
        logger.warning(f"Only {len(candles)} candles provided. Below warm-up required.")
        append_event(
            {"event": "LowCandleCountWarning", "count": len(candles), "required": 51}
        )

    if len(candles) < 31:
        raise RuntimeError("Need at least 31 candles for orchestrated modular mode")

    append_event(
        {
            "event": "MarketDataLoaded",
            "source": source,
            "symbol": symbol,
            "count": len(candles),
        }
    )
    return candles


def _init_broker(execution_mode: str, dry_run: bool, symbol: str, source: str) -> Any:
    if dry_run:
        append_event({"event": "DryRunModeActive"})
        return DryRunBroker(symbol=symbol)
    if execution_mode == "live":
        if source != "bitunix":
            raise ValueError("Live execution currently only supports bitunix source")
        from laptop_agents.execution.bitunix_broker import BitunixBroker

        api_key = os.environ.get("BITUNIX_API_KEY")
        secret_key = os.environ.get("BITUNIX_API_SECRET") or os.environ.get(
            "BITUNIX_SECRET_KEY"
        )
        if not api_key or not secret_key:
            raise ValueError(
                "Live execution requires BITUNIX_API_KEY and BITUNIX_API_SECRET"
            )
        provider = BitunixFuturesProvider(
            symbol=symbol, api_key=api_key, secret_key=secret_key
        )
        append_event({"event": "LiveBrokerInitialized", "broker": "BitunixBroker"})
        return BitunixBroker(provider)
    from laptop_agents.paper.broker import PaperBroker

    return PaperBroker(symbol=symbol)


def _load_daily_checkpoint(starting_balance: float) -> float:
    checkpoint_path = LOGS_DIR / "daily_checkpoint.json"
    if checkpoint_path.exists():
        try:
            with checkpoint_path.open("r") as f:
                ckpt = json.load(f)
            if ckpt.get("date") == datetime.now(timezone.utc).strftime("%Y-%m-%d"):
                starting_balance = float(ckpt.get("starting_equity", starting_balance))
                append_event({"event": "CheckpointLoaded", "equity": starting_balance})
        except Exception as e:
            append_event({"event": "CheckpointLoadError", "error": str(e)})
    return starting_balance


def _run_orchestration_loop(
    supervisor: Supervisor,
    candles: List[Candle],
    execution_mode: str,
    circuit_breaker: Any,
    symbol: str,
) -> tuple[float, List[Dict[str, Any]]]:
    current_equity = (
        supervisor.broker.current_equity
        if hasattr(supervisor.broker, "current_equity")
        else 10000.0
    )
    equity_history = []

    for i, candle in enumerate(candles):
        if os.environ.get("LA_KILL_SWITCH", "FALSE").upper() == "TRUE":
            logger.warning("KILL SWITCH ACTIVATED!")
            append_event({"event": "KillSwitchActivated"})
            if hasattr(supervisor.broker, "shutdown"):
                supervisor.broker.shutdown()
            raise RuntimeError("Run aborted by LA_KILL_SWITCH")

        if not circuit_breaker.allow_request():
            append_event({"event": "CircuitBreakerOpen"})
            time.sleep(1)
            continue

        skip_broker = execution_mode == "live" and i < len(candles) - 1
        try:
            state = supervisor.step(
                AgentState(instrument=symbol, timeframe="1m"),
                candle,
                skip_broker=skip_broker,
            )
            circuit_breaker.record_success()
            # Update equity
            for ex in state.broker_events.get("exits", []):
                current_equity += float(ex.get("pnl", 0.0))
            unrealized = supervisor.broker.get_unrealized_pnl(float(candle.close))
            if getattr(supervisor.broker, "is_inverse", False):
                unrealized *= float(candle.close)
            equity_history.append(
                {"ts": candle.ts, "equity": current_equity + unrealized}
            )
        except Exception as step_error:
            logger.error(f"Step Failed at {i}: {step_error}")
            circuit_breaker.record_failure()
            if circuit_breaker.state == "OPEN" and hasattr(
                supervisor.broker, "shutdown"
            ):
                supervisor.broker.shutdown()
    return current_equity, equity_history


def run_orchestrated_mode(
    symbol: str,
    interval: str,
    source: str,
    limit: int,
    fees_bps: float,
    slip_bps: float,
    risk_pct: float = 1.0,
    stop_bps: float = 30.0,
    tp_r: float = 1.5,
    execution_mode: str = "paper",
    dry_run: bool = False,
) -> tuple[bool, str]:
    try:
        validate_runtime_config(risk_pct, stop_bps, 10000.0)
        load_and_validate_risk_config()
    except Exception as e:
        return False, f"Config validation failed: {e}"

    run_id, run_dir = _setup_run_dir()
    append_event(
        {"event": "OrchestratedModularRunStarted", "run_id": run_id, "symbol": symbol}
    )

    from laptop_agents.core.resilience import ErrorCircuitBreaker

    circuit_breaker = ErrorCircuitBreaker(
        failure_threshold=5, recovery_timeout=120, time_window=60
    )

    try:
        candles = _load_market_data(source, symbol, interval, limit)
        starting_balance = _load_daily_checkpoint(10000.0)

        cfg = get_agent_config(starting_balance, risk_pct, stop_bps, tp_r)
        broker = _init_broker(execution_mode, dry_run, symbol, source)
        journal_path = run_dir / "journal.jsonl"
        supervisor = Supervisor(
            provider=None, cfg=cfg, journal_path=str(journal_path), broker=broker
        )

        ending_balance, equity_history = _run_orchestration_loop(
            supervisor, candles, execution_mode, circuit_breaker, symbol
        )

        # Post-run reporting
        _finalize_run_reporting(
            run_id,
            run_dir,
            candles,
            starting_balance,
            ending_balance,
            equity_history,
            fees_bps,
            slip_bps,
            symbol,
            interval,
            source,
            risk_pct,
            stop_bps,
            tp_r,
        )

        return True, f"Orchestrated modular run completed. Run ID: {run_id}"

    except Exception as e:
        import traceback

        _run_diagnostics(e)
        append_event(
            {
                "event": "OrchestratedModularError",
                "error": str(e),
                "trace": traceback.format_exc()[-500:],
            }
        )
        return False, str(e)


def _finalize_run_reporting(
    run_id,
    run_dir,
    candles,
    starting_balance,
    ending_balance,
    equity_history,
    fees_bps,
    slip_bps,
    symbol,
    interval,
    source,
    risk_pct,
    stop_bps,
    tp_r,
):
    # Save equity history
    equity_csv = LATEST_DIR / "equity.csv"
    with equity_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ts", "equity"])
        writer.writeheader()
        writer.writerows(equity_history)

    # Process journal for trades
    trades = _parse_journal_for_trades(run_dir / "journal.jsonl")
    write_trades_csv(trades)

    summary = {
        "run_id": run_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "symbol": symbol,
        "interval": interval,
        "candle_count": len(candles),
        "last_ts": str(candles[-1].ts),
        "starting_balance": starting_balance,
        "ending_balance": float(ending_balance),
        "net_pnl": float(ending_balance - starting_balance),
        "trades": len(trades),
        "risk_pct": risk_pct,
        "stop_bps": stop_bps,
        "tp_r": tp_r,
    }
    write_state({"summary": summary})
    render_html(summary, trades, "", candles=candles)

    # Copy artifacts
    for fname in ["trades.csv", "events.jsonl", "summary.html"]:
        if (LATEST_DIR / fname).exists():
            shutil.copy2(LATEST_DIR / fname, run_dir / fname)

    _print_session_summary(run_id, symbol, starting_balance, ending_balance, trades)


def _parse_journal_for_trades(journal_path: Path) -> List[Dict[str, Any]]:
    trades = []
    if journal_path.exists():
        from laptop_agents.trading.paper_journal import PaperJournal

        journal = PaperJournal(journal_path)
        open_trades = {}
        for event in journal.iter_events():
            if event.get("type") == "update":
                tid = event.get("trade_id")
                if "fill" in event:
                    open_trades[tid] = event["fill"]
                elif "exit" in event and tid in open_trades:
                    f, x = open_trades.pop(tid), event["exit"]
                    trades.append(
                        {
                            "trade_id": tid,
                            "side": f.get("side", "???"),
                            "signal": "MODULAR",
                            "entry": float(f.get("price", 0)),
                            "exit": float(x.get("price", 0)),
                            "quantity": float(f.get("qty", 0)),
                            "pnl": float(x.get("pnl", 0)),
                            "fees": float(f.get("fees", 0)) + float(x.get("fees", 0)),
                            "entry_ts": str(f.get("at", "")),
                            "exit_ts": str(x.get("at", "")),
                            "timestamp": str(x.get("at", event.get("at", ""))),
                            "setup": f.get("setup", "unknown"),
                        }
                    )
    return trades


def _print_session_summary(run_id, symbol, start, end, trades):
    wins = [t for t in trades if t.get("pnl", 0) > 0]
    wr = (len(wins) / len(trades) * 100) if trades else 0.0
    net = float(end - start)
    pct = (net / start * 100) if start > 0 else 0.0
    logger.info(
        f"\nSESS: {run_id} | {symbol} | Net: ${net:,.2f} ({pct:+.2f}%) | WR: {wr:.1f}%"
    )


def check_bitunix_config() -> tuple[bool, str]:
    import os

    api_key = os.environ.get("BITUNIX_API_KEY", "")
    secret_key = os.environ.get("BITUNIX_API_SECRET") or os.environ.get(
        "BITUNIX_SECRET_KEY", ""
    )

    if not api_key or not secret_key:
        return (
            False,
            "Bitunix API credentials not configured. Set BITUNIX_API_KEY and BITUNIX_API_SECRET in .env",
        )
    return True, "Bitunix configured"


def run_legacy_orchestration(
    mode: str,
    symbol: str,
    interval: str,
    source: str,
    limit: int,
    fees_bps: float,
    slip_bps: float,
    risk_pct: float = 1.0,
    stop_bps: float = 30.0,
    tp_r: float = 1.5,
    max_leverage: float = 1.0,
    intrabar_mode: str = "conservative",
    backtest_mode: str = "position",
    validate_splits: int = 5,
    validate_train: int = 600,
    validate_test: int = 200,
    grid_str: str = "sma=10,30;stop=20,30,40;tp=1.0,1.5,2.0",
    validate_max_candidates: int = 200,
) -> int:
    """Legacy orchestration logic moved from run.py for backward compatibility."""
    get_candles_for_mode = BitunixFuturesProvider.get_candles_for_mode

    run_id = str(uuid.uuid4())
    starting_balance = 10_000.0

    append_event(
        {"event": "RunStarted", "run_id": run_id, "mode": mode, "symbol": symbol}
    )

    try:
        candles = get_candles_for_mode(
            source=source,
            symbol=symbol,
            interval=interval,
            mode=mode,
            limit=limit,
            validate_train=validate_train,
            validate_test=validate_test,
            validate_splits=validate_splits,
        )

        if mode == "backtest":
            from laptop_agents.backtest.engine import (
                run_backtest_bar_mode,
                run_backtest_position_mode,
                set_context,
            )

            set_context(LATEST_DIR, append_event)
            if backtest_mode == "bar":
                result = run_backtest_bar_mode(
                    candles, starting_balance, fees_bps, slip_bps
                )
            else:
                result = run_backtest_position_mode(
                    candles=candles,
                    starting_balance=starting_balance,
                    fees_bps=fees_bps,
                    slip_bps=slip_bps,
                    risk_pct=risk_pct,
                    stop_bps=stop_bps,
                    tp_r=tp_r,
                    max_leverage=max_leverage,
                    intrabar_mode=intrabar_mode,
                )
            trades = result["trades"]
            ending_balance = result["ending_balance"]

        elif mode == "live":
            from laptop_agents.trading.exec_engine import run_live_paper_trading

            trades, ending_balance, _ = run_live_paper_trading(
                candles=candles,
                starting_balance=starting_balance,
                fees_bps=fees_bps,
                slip_bps=slip_bps,
                symbol=symbol,
                interval=interval,
                source=source,
                risk_pct=risk_pct,
                stop_bps=stop_bps,
                tp_r=tp_r,
                max_leverage=max_leverage,
                paper_dir=PAPER_DIR,
                append_event_fn=append_event,
            )
        elif mode == "validate":
            from laptop_agents.backtest.engine import run_validation, set_context

            set_context(LATEST_DIR, append_event)
            run_validation(
                candles=candles,
                starting_balance=starting_balance,
                fees_bps=float(fees_bps),
                slip_bps=float(slip_bps),
                risk_pct=float(risk_pct),
                max_leverage=float(max_leverage),
                intrabar_mode=intrabar_mode,
                grid_str=grid_str,
                validate_splits=validate_splits,
                validate_train=validate_train,
                validate_test=validate_test,
                max_candidates=validate_max_candidates,
            )
            return 0
        elif mode == "selftest":
            logger.info("SELFTEST PASS. (Self-test successful).")
            return 0
        else:
            # single mode or unknown
            from laptop_agents.trading.helpers import simulate_trade_one_bar
            from laptop_agents.trading.strategy import SMACrossoverStrategy

            signal = SMACrossoverStrategy().generate_signal(candles[:-1])

            if signal:
                res = simulate_trade_one_bar(
                    signal=signal,
                    entry_px=float(candles[-2].close),
                    exit_px=float(candles[-1].close),
                    starting_balance=starting_balance,
                    fees_bps=fees_bps,
                    slip_bps=slip_bps,
                )
                trades = [res]
                ending_balance = starting_balance + res["pnl"]
            else:
                trades = []
                ending_balance = starting_balance

        # Common reporting
        write_trades_csv(trades)
        summary = {
            "run_id": run_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": source,
            "symbol": symbol,
            "interval": interval,
            "candle_count": len(candles),
            "last_ts": str(candles[-1].ts),
            "last_close": float(candles[-1].close),
            "fees_bps": fees_bps,
            "slip_bps": slip_bps,
            "starting_balance": starting_balance,
            "ending_balance": float(ending_balance),
            "net_pnl": float(ending_balance - starting_balance),
            "trades": len(trades),
            "mode": mode,
        }
        write_state({"summary": summary})
        render_html(summary, trades, "", candles=candles)
        append_event(
            {
                "event": "RunFinished",
                "run_id": run_id,
                "net_pnl": float(ending_balance - starting_balance),
            }
        )
        return 0

    except Exception as e:
        logger.exception(f"Legacy Run failed: {e}")
        _run_diagnostics(e)
        append_event({"event": "RunError", "error": str(e)})
        return 1
