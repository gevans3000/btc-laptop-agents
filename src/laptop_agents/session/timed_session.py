"""
Timed Session Runner for Autonomous Trading.
Runs a polling loop for a specified duration, fetching candles and executing trades.
"""

from __future__ import annotations

import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from laptop_agents.core.logger import logger
from laptop_agents.core.orchestrator import append_event, PAPER_DIR
from laptop_agents.data.loader import load_bitunix_candles, load_mock_candles
from laptop_agents.paper.broker import PaperBroker
from laptop_agents.resilience.error_circuit_breaker import ErrorCircuitBreaker
from laptop_agents.trading.signal import generate_signal
from laptop_agents.trading.helpers import normalize_candle_order


@dataclass
class SessionResult:
    """Result of a timed trading session."""

    iterations: int = 0
    trades: int = 0
    errors: int = 0
    starting_equity: float = 10000.0
    ending_equity: float = 10000.0
    duration_sec: float = 0.0
    stopped_reason: str = "completed"


class GracefulShutdown:
    """Context manager for graceful shutdown handling."""

    def __init__(self):
        self.shutdown_requested = False
        self._original_sigint = None
        self._original_sigterm = None

    def __enter__(self):
        self._original_sigint = signal.getsignal(signal.SIGINT)
        self._original_sigterm = signal.getsignal(signal.SIGTERM)
        signal.signal(signal.SIGINT, self._handler)
        signal.signal(signal.SIGTERM, self._handler)
        return self

    def __exit__(self, *args):
        signal.signal(signal.SIGINT, self._original_sigint)
        signal.signal(signal.SIGTERM, self._original_sigterm)

    def _handler(self, signum, frame):
        logger.info(
            f"Shutdown signal received ({signum}). Finishing current iteration..."
        )
        self.shutdown_requested = True


def run_timed_session(
    duration_min: int = 10,
    poll_interval_sec: int = 60,
    symbol: str = "BTCUSDT",
    interval: str = "1m",
    source: str = "bitunix",
    limit: int = 200,
    starting_balance: float = 10000.0,
    risk_pct: float = 1.0,
    stop_bps: float = 30.0,
    tp_r: float = 1.5,
    execution_mode: str = "paper",
    fees_bps: float = 2.0,
    slip_bps: float = 0.5,
    strategy_config: Optional[Dict[str, Any]] = None,
) -> SessionResult:
    """
    Run an autonomous trading session for a specified duration.

    Args:
        duration_min: Session duration in minutes
        poll_interval_sec: Seconds between polls (default 60 for 1m candles)
        symbol: Trading symbol
        interval: Candle interval
        source: Data source ("bitunix" or "mock")
        limit: Number of candles to fetch per poll
        starting_balance: Initial paper balance
        risk_pct: Risk percentage per trade
        stop_bps: Stop loss in basis points
        tp_r: Take profit R-multiple

    Returns:
        SessionResult with session statistics
    """
    result = SessionResult(starting_equity=starting_balance)
    start_time = time.time()
    end_time = start_time + (duration_min * 60)

    # Initialize components
    broker: Any = None
    if execution_mode == "live":
        from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider
        from laptop_agents.execution.bitunix_broker import BitunixBroker
        import os

        api_key = os.environ.get("BITUNIX_API_KEY")
        secret_key = os.environ.get("BITUNIX_API_SECRET") or os.environ.get(
            "BITUNIX_SECRET_KEY"
        )

        if not api_key or not secret_key:
            raise ValueError(
                "Live execution requires BITUNIX_API_KEY and BITUNIX_API_SECRET environment variables"
            )

        provider = BitunixFuturesProvider(
            symbol=symbol, api_key=api_key, secret_key=secret_key
        )
        broker = BitunixBroker(provider)
        logger.info(f"Live session initialized with BitunixBroker for {symbol}")
    else:
        state_path = str(PAPER_DIR / "broker_state.json")
        broker = PaperBroker(
            symbol=symbol,
            fees_bps=fees_bps,
            slip_bps=slip_bps,
            starting_equity=starting_balance,
            state_path=state_path,
        )

    circuit_breaker = ErrorCircuitBreaker(
        failure_threshold=5, recovery_timeout=120, time_window=60
    )

    current_equity = starting_balance

    # Log session start
    append_event(
        {
            "event": "TimedSessionStarted",
            "duration_min": duration_min,
            "poll_interval_sec": poll_interval_sec,
            "symbol": symbol,
            "source": source,
            "starting_equity": starting_balance,
        },
        paper=True,
    )

    logger.info(
        f"Starting {duration_min}-minute session | Symbol: {symbol} | Source: {source}"
    )

    with GracefulShutdown() as shutdown:
        iteration = 0

        # Alignment: Wait for the top of the next minute if we are doing 1m candles
        if interval == "1m" and duration_min >= 2:
            now = time.time()
            sleep_sec = 60 - (now % 60)
            if sleep_sec > 2:  # Only sleep if we have more than 2 seconds to wait
                logger.info(f"Aligning to next minute... Sleeping for {sleep_sec:.1f}s")
                time.sleep(sleep_sec)

        while time.time() < end_time:
            # Check for kill switch
            kill_file = Path("kill.txt")
            if kill_file.exists():
                logger.warning("KILL SWITCH ACTIVATED: kill.txt detected")
                try:
                    kill_file.unlink()
                except Exception:
                    pass
                result.stopped_reason = "kill_switch"
                break

            # Check for shutdown request
            if shutdown.shutdown_requested:
                result.stopped_reason = "shutdown_requested"
                break

            # Check duration limit
            if time.time() >= end_time:
                result.stopped_reason = "duration_limit_reached"
                break

            # Check circuit breaker
            if not circuit_breaker.allow_request():
                result.stopped_reason = "circuit_breaker_open"
                append_event(
                    {
                        "event": "SessionStoppedByCircuitBreaker",
                        "status": {"state": circuit_breaker.state},
                    },
                    paper=True,
                )
                break

            iteration += 1
            result.iterations = iteration

            try:
                # Fetch fresh candles
                if source == "bitunix":
                    candles = load_bitunix_candles(symbol, interval, limit)
                else:
                    candles = load_mock_candles(limit)

                candles = normalize_candle_order(candles)

                if len(candles) < 31:
                    logger.warning(
                        f"Iteration {iteration}: Only {len(candles)} candles, skipping"
                    )
                    continue

                latest_candle = candles[-1]

                # Generate signal using strategy config if provided
                if strategy_config:
                    from laptop_agents.agents.supervisor import Supervisor
                    from laptop_agents.agents.state import State as AgentState

                    # Fix: Supervisor requires a valid string path for JournalCoachAgent
                    journal_path = str(PAPER_DIR / "live_session_journal.jsonl")
                    supervisor = Supervisor(
                        provider=None,
                        cfg=strategy_config,
                        journal_path=journal_path,
                        broker=broker,
                    )
                    state = AgentState(
                        instrument=symbol, timeframe=interval, candles=candles[:-1]
                    )
                    state = supervisor.step(state, candles[-1], skip_broker=True)
                    circuit_breaker.record_success()

                    # Extract signal from agent state
                    if state.setup.get("side") in ["LONG", "SHORT"]:
                        raw_signal = "BUY" if state.setup["side"] == "LONG" else "SELL"
                    else:
                        raw_signal = None
                else:
                    # Fallback to legacy signal generation
                    raw_signal = generate_signal(candles[:-1])

                # Build order if signal present
                order = None
                if raw_signal:
                    # Translate string signal to dict format for the runner
                    signal_side = "LONG" if raw_signal == "BUY" else "SHORT"

                    # Calculate position size
                    risk_amount = current_equity * (risk_pct / 100.0)
                    stop_distance = float(latest_candle.close) * (stop_bps / 10000.0)

                    # Guard against division by zero or invalid stop distance
                    if stop_distance <= 0:
                        logger.warning(
                            f"Invalid stop_distance={stop_distance:.6f} (stop_bps={stop_bps}, "
                            f"close={latest_candle.close}), skipping order"
                        )
                        append_event(
                            {
                                "event": "OrderSkipped",
                                "reason": "invalid_stop_distance",
                                "stop_distance": stop_distance,
                                "stop_bps": stop_bps,
                                "candle_close": float(latest_candle.close),
                                "iteration": iteration,
                            },
                            paper=True,
                        )
                    else:
                        qty = risk_amount / stop_distance

                        order = {
                            "go": True,
                            "side": signal_side,
                            "entry_type": "market",
                            "entry": float(latest_candle.close),
                            "qty": qty,
                            "sl": (
                                float(latest_candle.close) - stop_distance
                                if signal_side == "LONG"
                                else float(latest_candle.close) + stop_distance
                            ),
                            "tp": (
                                float(latest_candle.close) + (stop_distance * tp_r)
                                if signal_side == "LONG"
                                else float(latest_candle.close) - (stop_distance * tp_r)
                            ),
                            "equity": current_equity,
                        }

                # Execute via broker
                if order:
                    order["client_order_id"] = f"ord_{int(time.time())}_{iteration}"

                events = broker.on_candle(latest_candle, order)

                # Track trades
                for fill in events.get("fills", []):
                    result.trades += 1
                    append_event(
                        {
                            "event": "TradeFill",
                            "iteration": iteration,
                            **fill,
                        },
                        paper=True,
                    )

                for exit_event in events.get("exits", []):
                    pnl = float(exit_event.get("pnl", 0.0))
                    current_equity += pnl
                    append_event(
                        {
                            "event": "TradeExit",
                            "iteration": iteration,
                            **exit_event,
                        },
                        paper=True,
                    )

                # Calculate total equity including unrealized
                unrealized = broker.get_unrealized_pnl(float(latest_candle.close))
                total_equity = current_equity + unrealized

                # Heartbeat event
                append_event(
                    {
                        "event": "Heartbeat",
                        "iteration": iteration,
                        "candle_ts": latest_candle.ts,
                        "candle_close": float(latest_candle.close),
                        "equity": total_equity,
                        "realized_equity": current_equity,
                        "unrealized_pnl": unrealized,
                        "position": broker.pos.side if broker.pos else "FLAT",
                        "circuit_breaker": {"state": circuit_breaker.state},
                        "signal": raw_signal,
                        "elapsed_sec": time.time() - start_time,
                        "remaining_sec": end_time - time.time(),
                    },
                    paper=True,
                )

                remaining = end_time - time.time()
                position_str = broker.pos.side if broker.pos else "FLAT"
                signal_str = raw_signal if raw_signal else "NONE"

                logger.info(
                    f"[{iteration:03d}] {symbol} @ {float(latest_candle.close):,.2f} | "
                    f"Signal: {signal_str:5} | Pos: {position_str:5} | "
                    f"Equity: ${total_equity:,.2f} | "
                    f"Remaining: {remaining/60:.1f}m"
                )

            except Exception as e:
                result.errors += 1
                circuit_breaker.record_failure()
                logger.error(f"Iteration {iteration} error: {e}")
                append_event(
                    {
                        "event": "IterationError",
                        "iteration": iteration,
                        "error": str(e),
                    },
                    paper=True,
                )

            # Wait for next poll (but check for shutdown more frequently)
            wait_until = time.time() + poll_interval_sec
            while time.time() < wait_until and time.time() < end_time:
                if shutdown.shutdown_requested:
                    break
                time.sleep(1)  # Check every second

        # Shutdown cleanup (Cancel orders, close positions)
        if hasattr(broker, "shutdown"):
            try:
                # If we have a position, try to close it at the final price
                if hasattr(broker, "close_all") and broker.pos:
                    broker.close_all(float(candles[-1].close))
                broker.shutdown()
            except Exception as e:
                logger.error(f"Error during broker shutdown: {e}")

    # Finalize
    result.ending_equity = current_equity
    result.duration_sec = time.time() - start_time

    # Session complete event
    append_event(
        {
            "event": "TimedSessionCompleted",
            "iterations": result.iterations,
            "trades": result.trades,
            "errors": result.errors,
            "starting_equity": result.starting_equity,
            "ending_equity": result.ending_equity,
            "net_pnl": result.ending_equity - result.starting_equity,
            "duration_sec": result.duration_sec,
            "stopped_reason": result.stopped_reason,
        },
        paper=True,
    )

    summary = f"""
========== SESSION COMPLETE ==========
Duration:   {result.duration_sec / 60:.1f} minutes
Iterations: {result.iterations}
Trades:     {result.trades}
Errors:     {result.errors}
Start:      ${result.starting_equity:,.2f}
End:        ${result.ending_equity:,.2f}
Net PnL:    ${result.ending_equity - result.starting_equity:,.2f}
Stopped:    {result.stopped_reason}
=======================================
"""
    logger.info(summary)
    print(summary)

    return result
