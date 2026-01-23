from __future__ import annotations

import asyncio
import signal
import time
import threading
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from laptop_agents.core.logger import logger
from laptop_agents.core.orchestrator import (
    append_event,
)
from laptop_agents.session.heartbeat import heartbeat_task
from laptop_agents.trading.helpers import (
    Candle,
    Tick,
)
from laptop_agents import constants as hard_limits
from laptop_agents.constants import (
    DEFAULT_SYMBOL,
    REPO_ROOT,
    WORKSPACE_DIR,
    WORKSPACE_LOCKS_DIR,
    WORKSPACE_PAPER_DIR,
)
from laptop_agents.session.session_state import (
    AsyncSessionResult,
    build_session_result,
    restore_starting_balance,
)
from laptop_agents.session.funding import funding_task
from laptop_agents.session.execution import execution_task
from laptop_agents.session.stale_data import stale_data_task
from laptop_agents.session.watchdog import watchdog_tick_task, threaded_watchdog
from laptop_agents.session.kill_switch import kill_switch_task
from laptop_agents.session.timer import timer_task
from laptop_agents.session.checkpoint import checkpoint_task
from laptop_agents.session.market_data import market_data_task
from laptop_agents.session.seeding import seed_historical_candles
from laptop_agents.session.reporting import (
    export_metrics,
    generate_final_reports,
    generate_html_report,
)
from laptop_agents.core.state_manager import StateManager
from laptop_agents.core.resilience import ErrorCircuitBreaker
from laptop_agents.core.lock_manager import LockManager
from laptop_agents.paper.broker import PaperBroker
from laptop_agents.execution.bitunix_broker import BitunixBroker
from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider
from laptop_agents.core.config_models import StrategyConfig
from laptop_agents.agents.supervisor import Supervisor
from laptop_agents.agents.state import State as AgentState
from laptop_agents.backtest.replay_runner import ReplayProvider
from laptop_agents.data.providers.mock import MockProvider


class AsyncRunner:
    """Orchestrates the async event loop for trading."""

    def __init__(
        self,
        symbol: str,
        interval: str,
        strategy_config: Optional[Dict[str, Any]] = None,
        starting_balance: float = 10000.0,
        risk_pct: float = 1.0,
        stop_bps: float = 30.0,
        tp_r: float = 1.5,
        fees_bps: float = 2.0,
        slip_bps: float = 0.5,
        stale_timeout: int = 120,
        execution_latency_ms: int = 200,
        dry_run: bool = False,
        provider: Any = None,
        execution_mode: str = "paper",
        state_dir: Optional[Path] = None,
    ):
        self.symbol = symbol
        self.interval = interval
        self.strategy_config = strategy_config
        self.starting_equity = starting_balance
        self.risk_pct = risk_pct
        self.stop_bps = stop_bps
        self.tp_r = tp_r
        self.dry_run = dry_run
        self.duration_min = 0  # set in run()
        self.start_time = time.time()
        self.loop_id = uuid.uuid4().hex
        self.last_data_time = self.start_time
        self.last_heartbeat_time = self.start_time
        self.errors = 0
        self.iterations = 0
        self.trades = 0
        self.latest_tick: Optional[Tick] = None
        self.candles: List[Candle] = []
        self.metrics: List[Dict[str, Any]] = []
        self.shutdown_event = asyncio.Event()
        self.execution_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=100)
        self.stale_data_timeout_sec = float(stale_timeout)
        self.consecutive_ws_errors = 0
        self.stale_restart_attempts = 0
        self.max_stale_restarts = 3
        self.kill_file = WORKSPACE_DIR / "kill.txt"
        self.kill_switch_triggered = False
        self.execution_latency_ms = execution_latency_ms
        self.status = "initializing"
        self._shutting_down = False
        self._last_backfill_time = 0.0
        self._last_rest_poll_time = 0.0
        self.max_equity = starting_balance
        self.max_drawdown = 0.0
        self.stopped_reason = "completed"
        self._stop_event_emitted = False
        self._inflight_order_ids: set[str] = set()
        self.last_tick_ts: Optional[str] = None
        self.last_candle_ts: Optional[str] = None

        # Create session-specific workspace
        self.state_dir = Path(state_dir) if state_dir else WORKSPACE_PAPER_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.state_manager = StateManager(self.state_dir)

        # Components
        self.circuit_breaker = ErrorCircuitBreaker(
            failure_threshold=5, recovery_timeout=120, time_window=60
        )

        self.provider: Any = provider
        state_path = str(self.state_dir / "broker_state.db")

        self.broker: Union[PaperBroker, BitunixBroker]

        if execution_mode == "live":
            api_key = os.environ.get("BITUNIX_API_KEY")
            secret_key = os.environ.get("BITUNIX_API_SECRET") or os.environ.get(
                "BITUNIX_SECRET_KEY"
            )
            if not api_key or not secret_key:
                raise ValueError(
                    "Live execution requires BITUNIX_API_KEY and BITUNIX_API_SECRET environment variables"
                )
            live_provider = BitunixFuturesProvider(
                symbol=symbol, api_key=api_key, secret_key=secret_key
            )
            self.broker = BitunixBroker(live_provider, starting_equity=starting_balance)
            logger.info(f"Initialized BitunixBroker for live trading on {symbol}")
        else:
            self.broker = PaperBroker(
                symbol=symbol,
                fees_bps=fees_bps,
                slip_bps=slip_bps,
                starting_equity=starting_balance,
                state_path=state_path,
                strategy_config=self.strategy_config,
            )

        # Restore starting equity from broker (if it was NOT restored from unified state already)
        # If starting_balance is NOT the default, it means it was likely restored from unified state
        is_restored = starting_balance != 10000.0

        if not is_restored and self.broker.starting_equity is not None:
            logger.info(
                f"Restoring starting equity from broker state: ${self.broker.starting_equity:,.2f}"
            )
            self.starting_equity = self.broker.starting_equity
        else:
            # Sync broker to our master starting_equity
            self.broker.starting_equity = self.starting_equity

        # Ensure starting_equity is in state_manager for unified restoration
        self.state_manager.set("starting_equity", self.starting_equity)
        self.state_manager.save()

        # Reset stale drawdown state if no open exposure (avoid immediate kill switch)
        try:
            has_open_orders = bool(getattr(self.broker, "working_orders", []))
            if (
                self.broker.pos is None
                and not has_open_orders
                and self.starting_equity > 0
            ):
                drawdown_usd = self.starting_equity - float(self.broker.current_equity)
                if drawdown_usd >= hard_limits.MAX_DAILY_LOSS_USD:
                    logger.warning(
                        "STARTUP_DRAWDOWN_RESET: resetting starting equity after stale drawdown",
                        {
                            "event": "StartupDrawdownReset",
                            "symbol": self.symbol,
                            "loop_id": self.loop_id,
                            "position": "FLAT",
                            "open_orders_count": 0,
                            "starting_equity": self.starting_equity,
                            "current_equity": self.broker.current_equity,
                            "drawdown_usd": drawdown_usd,
                        },
                    )
                    self.starting_equity = float(self.broker.current_equity)
                    self.broker.starting_equity = self.starting_equity
                    self.state_manager.set("starting_equity", self.starting_equity)
                    self.state_manager.save()
        except Exception as e:
            logger.error(f"Failed to normalize startup equity: {e}")

        # 2.3 Config Validation on Startup
        if self.strategy_config:
            try:
                validated = StrategyConfig.validate_config(self.strategy_config)
                self.strategy_config = validated.model_dump()
                logger.info("Strategy configuration validated successfully.")

                # Pre-initialize supervisor and state for performance
                self.supervisor = Supervisor(
                    provider=None, cfg=self.strategy_config, broker=self.broker
                )
                self.agent_state = AgentState(
                    instrument=self.symbol, timeframe=self.interval
                )
            except Exception as e:
                logger.error(f"CONFIG_VALIDATION_FAILED: {e}")
                # Hard fail on startup as per Perfection Plan Phase 2.3
                raise ValueError(f"Invalid strategy configuration: {e}")

        # PID Tracking for external monitoring
        workspace_dir = REPO_ROOT / ".workspace"
        workspace_dir.mkdir(exist_ok=True)
        pid_file = workspace_dir / "agent.pid"
        with open(pid_file, "w") as f:
            f.write(str(os.getpid()))
        logger.info(f"PID {os.getpid()} written to {pid_file}")

    async def on_candle_closed(self, candle: Candle) -> None:
        """Runs strategy logic when a candle is confirmed closed."""
        from laptop_agents.session.strategy import on_candle_closed

        await on_candle_closed(self, candle)

    async def run(self, duration_min: int):
        """Main entry point to run the async loop."""
        self.duration_min = duration_min
        end_time = self.start_time + (duration_min * 60)
        self.status = "running"

        # Check circuit breaker state
        if not self.circuit_breaker.allow_request():
            logger.warning("Circuit breaker is OPEN. It remains OPEN.")
            self._request_shutdown("circuit_breaker_open")

        # Start Threaded Watchdog (independent of event loop)
        watchdog_thread = threading.Thread(
            target=threaded_watchdog, args=(self,), daemon=True
        )
        watchdog_thread.start()
        logger.info("Threaded watchdog started.")

        # Seed historical candles
        await seed_historical_candles(self)

        # Start tasks
        tasks = [
            asyncio.create_task(market_data_task(self)),
            asyncio.create_task(watchdog_tick_task(self)),
            asyncio.create_task(heartbeat_task(self)),
            asyncio.create_task(timer_task(self, end_time)),
            asyncio.create_task(kill_switch_task(self)),
            asyncio.create_task(stale_data_task(self)),
            asyncio.create_task(funding_task(self)),
            asyncio.create_task(execution_task(self)),
            asyncio.create_task(checkpoint_task(self)),
        ]
        for task in tasks:
            task.add_done_callback(self._handle_task_done)

        try:
            await self.shutdown_event.wait()
        finally:
            await self._perform_shutdown(tasks)

    async def _perform_shutdown(self, tasks: List[asyncio.Task]) -> None:
        """Handles the graceful shutdown sequence."""
        if self._shutting_down:
            return
        self._shutting_down = True
        self.status = "shutting_down"
        logger.info("GRACEFUL SHUTDOWN INITIATED")

        if not self._stop_event_emitted:
            try:
                append_event(
                    {
                        "event": "SessionStopped",
                        "reason": self.stopped_reason,
                        "errors": self.errors,
                        "symbol": self.symbol,
                        "interval": self.interval,
                    },
                    paper=True,
                )
                self._stop_event_emitted = True
            except Exception as e:
                logger.error(f"Failed to append SessionStopped event: {e}")

        # 2. Cancel all open orders (alias in PaperBroker)
        try:
            self.broker.cancel_all_open_orders()
        except Exception as e:
            logger.error(f"Failed to cancel orders: {e}")

        # 3. Wait up to 2s for pending fills
        try:
            await asyncio.sleep(2.0)
        except Exception:
            pass

        # 4. Queue Draining: Persist pending orders to broker state
        while not self.execution_queue.empty():
            try:
                item = self.execution_queue.get_nowait()
                order = item.get("order")
                if order:
                    working_orders = getattr(self.broker, "working_orders", None)
                    if isinstance(working_orders, list):
                        working_orders.append(order)
                    logger.info(
                        f"Drained pending order {order.get('client_order_id')} to broker state"
                    )
            except asyncio.QueueEmpty:
                break

        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        # Final cleanup
        if self.broker.pos:
            price = None
            if self.latest_tick:
                price = self.latest_tick.last
            elif self.candles:
                price = self.candles[-1].close
            if price and price > 0:
                self.broker.close_all(price)

        try:
            # Use task wrapper for shutdown to ensure it completes
            shutdown_task = asyncio.create_task(asyncio.to_thread(self.broker.shutdown))
            await asyncio.wait_for(asyncio.shield(shutdown_task), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Broker shutdown timed out after 5s")
        except Exception as e:
            logger.exception(f"Broker shutdown failed: {e}")

        try:
            self.state_manager.set_circuit_breaker_state(
                {"state": self.circuit_breaker.state}
            )
            self.state_manager.set("starting_equity", self.starting_equity)
            self.state_manager.save()
            logger.info("Final unified state saved.")
        except Exception as e:
            logger.error(f"Failed to save unified state on shutdown: {e}")

        # Reporting & Metrics
        export_metrics(self)
        generate_final_reports(self)

        logger.info("AsyncRunner shutdown complete.")

    def _parse_ts_to_int(self, ts: Any) -> int:
        """Robustly parse timestamp (int, float, or ISO string) to unix seconds."""
        try:
            if isinstance(ts, (int, float)):
                return int(ts)
            ts_str = str(ts)
            if ts_str.isdigit():
                return int(ts_str)
            if "T" in ts_str:
                return int(
                    datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
                )
        except Exception:
            pass
        return 0

    def _request_shutdown(self, reason: str) -> None:
        if not self.shutdown_event.is_set():
            if self.stopped_reason == "completed":
                self.stopped_reason = reason
            self.shutdown_event.set()

    def _handle_task_done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error(f"Task failed: {task.get_name()} | {exc}")
            self.errors += 1
            self._request_shutdown("task_failed")


async def run_async_session(
    duration_min: int = 10,
    symbol: str = DEFAULT_SYMBOL,
    interval: str = "1m",
    starting_balance: float = 10000.0,
    risk_pct: float = 1.0,
    stop_bps: float = 30.0,
    tp_r: float = 1.5,
    fees_bps: float = 2.0,
    slip_bps: float = 0.5,
    strategy_config: Optional[Dict[str, Any]] = None,
    stale_timeout: int = 120,
    execution_latency_ms: int = 200,
    dry_run: bool = False,
    replay_path: Optional[str] = None,
    execution_mode: str = "paper",
    state_dir: Optional[Path] = None,
) -> AsyncSessionResult:
    """Entry point for the async session."""

    effective_state_dir = Path(state_dir) if state_dir else WORKSPACE_PAPER_DIR

    # Startup Safety - PID Locking (single source of truth under .workspace/)
    WORKSPACE_LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    lock = LockManager(WORKSPACE_LOCKS_DIR / "async_session.pid")
    if not lock.acquire():
        logger.error(
            "Session already running (lock file exists: .workspace/locks/async_session.pid)"
        )
        return AsyncSessionResult(stopped_reason="already_running")

    # Reference Persistence: Restore starting_equity from local state if available
    unified_state_path = effective_state_dir / "unified_state.json"
    original_starting_balance = starting_balance
    starting_balance = restore_starting_balance(unified_state_path, starting_balance)

    runner = None
    try:
        runner = AsyncRunner(
            symbol=symbol,
            interval=interval,
            strategy_config=strategy_config,
            starting_balance=starting_balance,
            risk_pct=risk_pct,
            stop_bps=stop_bps,
            tp_r=tp_r,
            fees_bps=fees_bps,
            slip_bps=slip_bps,
            stale_timeout=stale_timeout,
            execution_latency_ms=execution_latency_ms,
            dry_run=dry_run,
            provider=None,
            execution_mode=execution_mode,
            state_dir=effective_state_dir,
        )

        # Determine Provider based on config/path
        if replay_path:
            runner.provider = ReplayProvider(Path(replay_path))
            logger.info(f"Using REPLAY PROVIDER from {replay_path}")
        elif strategy_config and strategy_config.get("source") == "mock":
            runner.provider = MockProvider()
            logger.info("Using MOCK PROVIDER (simulated market data)")

        if runner.provider is None:
            runner.provider = BitunixFuturesProvider(symbol=symbol)
            logger.info(f"Using default BITUNIX WEBSOCKET PROVIDER for {symbol}")

        # Handle OS signals
        def handle_sigterm(signum, frame):
            logger.info(f"Signal {signum} received - Forcing broker close.")
            if runner and runner.broker and runner.latest_tick:
                try:
                    runner.broker.close_all(runner.latest_tick.last)
                except Exception as e:
                    logger.error(f"Failed to close positions on SIGTERM: {e}")
            if runner:
                runner.stopped_reason = "signal"
                runner._request_shutdown("signal")

        try:
            loop = asyncio.get_running_loop()
            if os.name != "nt":
                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.add_signal_handler(
                        sig, lambda: runner._request_shutdown("signal")
                    )
            else:
                # On Windows, use signal module for basic handlers
                signal.signal(signal.SIGINT, handle_sigterm)
                signal.signal(signal.SIGTERM, handle_sigterm)
        except (NotImplementedError, AttributeError, ValueError) as se:
            logger.warning(f"Signal handlers not fully supported: {se}")

        try:
            await runner.run(duration_min)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received. Initiating graceful shutdown...")
            runner._request_shutdown("keyboard_interrupt")
            # Give it a moment to clean up
            await asyncio.sleep(1.0)
        except Exception as e:
            logger.error(f"Fatal error in async session run: {e}")
            runner.errors += 1

        # Generate HTML report
        generate_html_report(runner, original_starting_balance)

    except Exception as top_e:
        logger.error(f"Fatal error in async session setup: {top_e}")
    finally:
        try:
            lock.release()
        except Exception:
            pass

    if runner:
        return build_session_result(runner)
    else:
        return AsyncSessionResult(stopped_reason="init_failed")
