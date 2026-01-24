import uuid
from datetime import datetime

from laptop_agents.core.logger import logger
from laptop_agents.core.events import append_event, LATEST_DIR, PAPER_DIR
from laptop_agents.core.orchestrator import _run_diagnostics
from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider
from laptop_agents.reporting.service import (
    write_trades_csv,
    write_state,
    render_html,
)


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
    """Legacy orchestration logic moved from orchestrator.py for backward compatibility."""
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
