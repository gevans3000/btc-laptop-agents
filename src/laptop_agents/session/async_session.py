from __future__ import annotations

import asyncio
import signal
import time
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from laptop_agents.core.logger import logger
from laptop_agents.trading.helpers import (
    Candle,
    Tick,
)
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
from laptop_agents.session.lifecycle import (
    run_session_lifecycle,
    request_shutdown,
)
from laptop_agents.session.reporting import (
    generate_html_report,
)
from laptop_agents.core.state_manager import StateManager
from laptop_agents.core.resilience import ErrorCircuitBreaker
from laptop_agents.core.lock_manager import LockManager
from laptop_agents.data.providers.bitunix_futures import BitunixFuturesProvider
from laptop_agents.core.config_models import StrategyConfig
from laptop_agents.agents.supervisor import Supervisor
from laptop_agents.agents.state import State as AgentState
from laptop_agents.backtest.replay_runner import ReplayProvider
from laptop_agents.data.providers.mock import MockProvider
from laptop_agents.data.provider_protocol import Provider


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
        provider: Optional[Provider] = None,
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

        self.provider: Optional[Provider] = provider
        state_path = str(self.state_dir / "broker_state.db")

        # 1. Broker Initialization via Factory
        from laptop_agents.session.broker_factory import create_broker

        self.broker = create_broker(
            execution_mode=execution_mode,
            symbol=symbol,
            starting_balance=starting_balance,
            fees_bps=fees_bps,
            slip_bps=slip_bps,
            state_path=state_path,
            strategy_config=self.strategy_config,
        )

        # 2. State Synchronization via Module
        from laptop_agents.session.state_sync import sync_initial_state

        self.starting_equity = sync_initial_state(self, starting_balance)

        # 2.3 Config Validation on Startup
        if self.strategy_config:
            try:
                validated = StrategyConfig.validate_config(self.strategy_config)
                self.strategy_config = validated.model_dump()
                logger.info("Strategy configuration validated successfully.")

                # Pre-initialize supervisor and state for performance
                instrument_info = None
                if self.provider:
                    try:
                        instrument_info = self.provider.get_instrument_info(self.symbol)
                        logger.info(
                            f"Instrument info fetched for {self.symbol}: {instrument_info}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch instrument info for {self.symbol}, using defaults: {e}"
                        )

                self.supervisor = Supervisor(
                    provider=self.provider,
                    cfg=self.strategy_config,
                    broker=self.broker,
                    instrument_info=instrument_info,
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

    async def run(self, duration_min: int) -> None:
        """Main entry point to run the async loop. Delegates to lifecycle module."""
        await run_session_lifecycle(self, duration_min)

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
        except Exception as e:
            logger.debug(f"Failed to parse timestamp {ts}: {e}")
        return 0

    def _request_shutdown(self, reason: str) -> None:
        """Request a graceful shutdown. Delegates to lifecycle module."""
        request_shutdown(self, reason)


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
        def handle_sigterm(signum: int, frame: Any) -> None:
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
        except (OSError, PermissionError) as e:
            logger.warning(f"Failed to release session lock: {e}")

    if runner:
        return build_session_result(runner)
    else:
        return AsyncSessionResult(stopped_reason="init_failed")
