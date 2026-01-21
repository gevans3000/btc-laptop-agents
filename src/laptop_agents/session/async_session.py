from __future__ import annotations

import asyncio
import json
import random
import signal
import time
import threading
import os
import psutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import math
from typing import Any, Dict, List, Optional, Union

from laptop_agents.data.providers.bitunix_ws import FatalError
from laptop_agents.core.logger import logger, write_alert
from laptop_agents.core.orchestrator import (
    append_event,
    render_html,
    LATEST_DIR,
)
from laptop_agents.trading.helpers import (
    Candle,
    Tick,
    DataEvent,
    normalize_candle_order,
)
from laptop_agents.data.loader import load_bitunix_candles
from laptop_agents.core import hard_limits
from laptop_agents.core.hard_limits import MAX_ERRORS_PER_SESSION
from laptop_agents.constants import DEFAULT_SYMBOL


@dataclass
class AsyncSessionResult:
    """Result of an async trading session."""

    iterations: int = 0
    trades: int = 0
    errors: int = 0
    starting_equity: float = 10000.0
    ending_equity: float = 10000.0
    duration_sec: float = 0.0
    max_drawdown: float = 0.0
    stopped_reason: str = "completed"


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
        from laptop_agents.constants import REPO_ROOT

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
        self.kill_file = REPO_ROOT / "kill.txt"
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
        self.state_dir = state_dir or Path("paper")
        self.state_dir.mkdir(exist_ok=True)

        from laptop_agents.core.state_manager import StateManager

        self.state_manager = StateManager(self.state_dir)

        # Components
        from laptop_agents.resilience.trading_circuit_breaker import (
            TradingCircuitBreaker,
        )

        self.circuit_breaker = TradingCircuitBreaker(
            max_daily_drawdown_pct=5.0, max_consecutive_losses=5
        )
        self.circuit_breaker.set_starting_equity(starting_balance)

        self.provider: Any = provider
        state_path = str(self.state_dir / "async_broker_state.json")
        from laptop_agents.paper.broker import PaperBroker
        from laptop_agents.execution.bitunix_broker import BitunixBroker

        self.broker: Union[PaperBroker, BitunixBroker]

        if execution_mode == "live":
            from laptop_agents.data.providers.bitunix_futures import (
                BitunixFuturesProvider,
            )

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
            self.circuit_breaker.set_starting_equity(self.starting_equity)
        else:
            # Sync broker to our master starting_equity
            self.broker.starting_equity = self.starting_equity
            self.circuit_breaker.set_starting_equity(self.starting_equity)

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
                    self.circuit_breaker.set_starting_equity(self.starting_equity)
                    self.state_manager.set("starting_equity", self.starting_equity)
                    self.state_manager.set_circuit_breaker_state({})
                    self.state_manager.save()
        except Exception as e:
            logger.error(f"Failed to normalize startup equity: {e}")

        # 2.3 Config Validation on Startup
        if self.strategy_config:
            try:
                from laptop_agents.core.config_models import StrategyConfig

                validated = StrategyConfig.validate_config(self.strategy_config)
                self.strategy_config = validated.model_dump()
                logger.info("Strategy configuration validated successfully.")

                # Pre-initialize supervisor and state for performance
                from laptop_agents.agents.supervisor import Supervisor
                from laptop_agents.agents.state import State as AgentState

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

    async def run(self, duration_min: int):
        """Main entry point to run the async loop."""
        self.duration_min = duration_min
        end_time = self.start_time + (duration_min * 60)
        self.status = "running"

        # Restore circuit breaker state
        cb_state = self.state_manager.get_circuit_breaker_state()
        if cb_state:
            logger.info("Restoring circuit breaker state...")
            self.circuit_breaker.restore_state(cb_state)
            if self.circuit_breaker.is_tripped():
                logger.warning(
                    f"Circuit breaker was previously TRIPPED ({self.circuit_breaker._trip_reason}). It remains TRIPPED."
                )
                self._request_shutdown("circuit_breaker_tripped")
                # Note: TradingCircuitBreaker doesn't have a direct 'trip()' method but is_tripped() checks state

        # Start Threaded Watchdog (independent of event loop)
        watchdog_thread = threading.Thread(target=self._threaded_watchdog, daemon=True)
        watchdog_thread.start()
        logger.info("Threaded watchdog started.")
        # Pre-load some historical candles if possible to seed strategy
        retry_count = 0
        min_history = 100
        if self.strategy_config:
            min_history = self.strategy_config.get("engine", {}).get(
                "min_history_bars", 100
            )

        # 1.1 Seeding Logic (Mock vs REST)
        if hasattr(self.provider, "history"):
            logger.info(
                f"Seeding historical candles from provider (count={min_history})..."
            )
            self.candles = self.provider.history(min_history)
        else:
            while retry_count < 5:
                try:
                    logger.info(
                        f"Seeding historical candles via REST (attempt {retry_count + 1}/5)..."
                    )
                    # Using max(100, min_history) logic from original
                    self.candles = load_bitunix_candles(
                        self.symbol, self.interval, limit=max(100, min_history)
                    )
                    self.candles = normalize_candle_order(self.candles)

                    if len(self.candles) >= min_history:
                        logger.info(f"Seed complete: {len(self.candles)} candles")
                        break
                    else:
                        logger.warning(
                            f"Incomplete seed: {len(self.candles)}/{min_history}. Retrying in 10s..."
                        )
                except Exception as e:
                    logger.warning(f"Seed attempt {retry_count + 1} failed: {e}")

                retry_count += 1
                if retry_count < 5:
                    await asyncio.sleep(10)

            if len(self.candles) < min_history:
                logger.error(
                    f"DEGRADED_START: Failed to seed historical candles after 5 attempts "
                    f"({len(self.candles)} < {min_history}). Starting with empty/partial history."
                )
                # Ensure we have at least an empty list if it failed completely
                if self.candles is None:
                    self.candles = []
                # Proceed without raising FatalError
            else:
                logger.info(f"Seed complete: {len(self.candles)} candles")

        from laptop_agents.trading.helpers import detect_candle_gaps

        gaps = detect_candle_gaps(self.candles, self.interval)
        for gap in gaps:
            logger.warning(
                f"GAP_DETECTED: {gap['missing_count']} missing between {gap['prev_ts']} and {gap['curr_ts']}"
            )

        # Start tasks
        tasks = [
            asyncio.create_task(self.market_data_task()),
            asyncio.create_task(self.watchdog_tick_task()),
            asyncio.create_task(self.heartbeat_task()),
            asyncio.create_task(self.timer_task(end_time)),
            asyncio.create_task(self.kill_switch_task()),
            asyncio.create_task(self.stale_data_task()),
            asyncio.create_task(self.funding_task()),
            asyncio.create_task(self.execution_task()),
            asyncio.create_task(self.checkpoint_task()),
        ]
        for task in tasks:
            task.add_done_callback(self._handle_task_done)

        try:
            await self.shutdown_event.wait()
        finally:
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

            # 3. Wait up to 5s for pending fills
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
                # Item 9: Use task wrapper for shutdown to ensure it completes
                shutdown_task = asyncio.create_task(
                    asyncio.to_thread(self.broker.shutdown)
                )
                await asyncio.wait_for(asyncio.shield(shutdown_task), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Broker shutdown timed out after 5s")
            except Exception as e:
                logger.exception(f"Broker shutdown failed: {e}")

            try:
                self.state_manager.set_circuit_breaker_state(
                    self.circuit_breaker.get_status()
                )
                self.state_manager.set("starting_equity", self.starting_equity)
                self.state_manager.save()
                logger.info("Final unified state saved.")
            except Exception as e:
                logger.error(f"Failed to save unified state on shutdown: {e}")

            logger.info("AsyncRunner shutdown complete.")

            # Export Metrics
            try:
                metrics_path = LATEST_DIR / "metrics.json"
                with open(metrics_path, "w") as f:
                    json.dump(self.metrics, f, indent=2)
                logger.info(f"Metrics exported to {metrics_path}")
            except Exception as me:
                logger.error(f"Failed to export metrics: {me}")

            # Export Metrics to CSV
            try:
                import csv

                csv_path = LATEST_DIR / "metrics.csv"
                if self.metrics:
                    with open(csv_path, "w", newline="") as f:
                        writer = csv.DictWriter(f, fieldnames=self.metrics[0].keys())
                        writer.writeheader()
                        writer.writerows(self.metrics)
                    logger.info(f"Metrics exported to {csv_path}")
            except Exception as ce:
                logger.error(f"Failed to export CSV metrics: {ce}")

            # 4.3 Session Summary Report
            try:
                from laptop_agents.reporting.summary import generate_summary

                summary = generate_summary(self.broker, self.start_time)
                summary_path = LATEST_DIR / "summary.json"
                with open(summary_path, "w") as f:
                    json.dump(summary, f, indent=2)
                logger.info(f"Session summary written to {summary_path}")
            except Exception as se:
                logger.error(f"Failed to generate summary: {se}")

            # Generate final_report.json
            try:
                report_path = LATEST_DIR / "final_report.json"
                exit_code = 0 if self.errors == 0 else 1
                report = {
                    "status": "success" if exit_code == 0 else "error",
                    "exit_code": exit_code,
                    "pnl_absolute": round(
                        self.broker.current_equity - self.starting_equity, 2
                    ),
                    "error_count": self.errors,
                    "duration_seconds": round(time.time() - self.start_time, 1),
                    "symbol": self.symbol,
                    "trades": self.trades,
                    "stopped_reason": self.stopped_reason,
                }
                with open(report_path, "w") as f:
                    json.dump(report, f, indent=2)
                logger.info(f"Final report written to {report_path}")

                # 3.3 Post-Run Performance Summary (CLI)
                trades_list = [
                    h for h in self.broker.order_history if h.get("type") == "exit"
                ]
                wins = [t for t in trades_list if t.get("pnl", 0) > 0]
                win_rate = (len(wins) / len(trades_list) * 100) if trades_list else 0.0
                total_fees = sum(t.get("fees", 0) for t in trades_list)
                net_pnl = float(self.broker.current_equity - self.starting_equity)
                pnl_pct = (
                    (net_pnl / self.starting_equity * 100)
                    if self.starting_equity > 0
                    else 0.0
                )

                summary_text = f"""
========== SESSION COMPLETE (ASYNC) ==========
Symbol:     {self.symbol}
Start:      ${self.starting_equity:,.2f}
End:        ${self.broker.current_equity:,.2f}
Net PnL:    ${net_pnl:,.2f} ({pnl_pct:+.2f}%)
--------------------------------------
Trades:     {len(trades_list)}
Win Rate:   {win_rate:.1f}%
Total Fees: ${total_fees:,.2f}
==============================================
"""
                logger.info(summary_text)
            except Exception as re:
                logger.error(f"CRITICAL: Failed to write final report/summary: {re}")

            if self.errors > 0:
                write_alert(f"Session failed with {self.errors} errors")

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
            pos_str = self.broker.pos.side if self.broker.pos else "FLAT"
            open_orders_count = len(getattr(self.broker, "working_orders", []))
            logger.error(
                "Background task failed",
                {
                    "event": "TaskFailed",
                    "symbol": self.symbol,
                    "loop_id": self.loop_id,
                    "position": pos_str,
                    "open_orders_count": open_orders_count,
                    "interval": self.interval,
                    "error": str(exc),
                },
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            self.errors += 1
            self._request_shutdown("task_failed")

    async def market_data_task(self):
        """Consumes WebSocket data and triggers strategy on candle closure."""
        while not self.shutdown_event.is_set():
            listener = None
            try:
                listener = self.provider.listen()
                while not self.shutdown_event.is_set():
                    try:
                        # Item 1: Timeout-aware iteration
                        item = await asyncio.wait_for(listener.__anext__(), timeout=5.0)
                    except asyncio.TimeoutError:
                        continue
                    except StopAsyncIteration:
                        break

                    if isinstance(item, DataEvent):
                        logger.warning(
                            f"RECEIVED_DATA_EVENT: {item.event} | {item.details}"
                        )
                        if item.event in ["ORDER_BOOK_STALE", "CIRCUIT_TRIPPED"]:
                            write_alert(f"MARKET_DATA_FAILED: {item.event}")
                            self._request_shutdown("market_data_failed")
                            break

                    if isinstance(item, Tick):
                        ts_sec = self._parse_ts_to_int(item.ts)
                        if ts_sec <= 0:
                            continue
                        last_ts_sec = (
                            self._parse_ts_to_int(self.last_tick_ts)
                            if self.last_tick_ts
                            else 0
                        )
                        if ts_sec <= last_ts_sec:
                            continue
                        if (time.time() - ts_sec) > self.stale_data_timeout_sec:
                            continue
                        # Robust Validation
                        bid = getattr(item, "bid", None)
                        ask = getattr(item, "ask", None)
                        last = getattr(item, "last", None)
                        if bid is None or ask is None or last is None:
                            continue
                        if any(
                            (not math.isfinite(x)) or x <= 0 for x in [bid, ask, last]
                        ):
                            continue
                        if bid > ask:
                            continue

                        self.latest_tick = item
                        self.last_tick_ts = item.ts
                        self.last_data_time = time.time()
                        self.stale_restart_attempts = 0
                        self.consecutive_ws_errors = 0

                    elif isinstance(item, Candle):
                        ts_sec = self._parse_ts_to_int(item.ts)
                        if ts_sec <= 0:
                            continue
                        last_ts_sec = (
                            self._parse_ts_to_int(self.last_candle_ts)
                            if self.last_candle_ts
                            else 0
                        )
                        if ts_sec <= last_ts_sec:
                            continue
                        if (time.time() - ts_sec) > self.stale_data_timeout_sec:
                            continue
                        open_val = getattr(item, "open", None)
                        high_val = getattr(item, "high", None)
                        low_val = getattr(item, "low", None)
                        close_val = getattr(item, "close", None)
                        if (
                            open_val is None
                            or high_val is None
                            or low_val is None
                            or close_val is None
                        ):
                            continue
                        if any(
                            (not math.isfinite(x)) or x <= 0
                            for x in [open_val, high_val, low_val, close_val]
                        ):
                            continue
                        if low_val > high_val:
                            continue
                        volume_val = getattr(item, "volume", None)
                        if volume_val is not None:
                            if (not math.isfinite(volume_val)) or volume_val < 0:
                                continue

                        self.consecutive_ws_errors = 0
                        self.last_candle_ts = item.ts
                        self.last_data_time = time.time()
                        self.stale_restart_attempts = 0
                        new_ts_sec = ts_sec

                        # Item 3 & 12: Fixed Gap-Detection & Rate Limiting
                        try:
                            interval_sec = {
                                "1m": 60,
                                "5m": 300,
                                "15m": 900,
                                "1h": 3600,
                            }.get(self.interval, 60)
                            if self.candles:
                                last_ts_sec = self._parse_ts_to_int(self.candles[-1].ts)
                                if (new_ts_sec - last_ts_sec) > interval_sec * 1.5:
                                    missing_count = int(
                                        (new_ts_sec - last_ts_sec) / interval_sec
                                    )
                                    now = time.time()
                                    if (
                                        missing_count > 0
                                        and (now - self._last_backfill_time) >= 30.0
                                    ):
                                        logger.warning(
                                            f"GAP_DETECTED: {missing_count} missing. Backfilling..."
                                        )
                                        try:
                                            fetched = await asyncio.to_thread(
                                                load_bitunix_candles,
                                                self.symbol,
                                                self.interval,
                                                min(missing_count + 5, 200),
                                            )
                                            self._last_backfill_time = (
                                                time.time()
                                            )  # Update AFTER success
                                            fetched = normalize_candle_order(fetched)
                                            for f_candle in fetched:
                                                f_ts_sec = self._parse_ts_to_int(
                                                    f_candle.ts
                                                )
                                                if last_ts_sec < f_ts_sec < new_ts_sec:
                                                    if f_candle.ts not in [
                                                        c.ts for c in self.candles
                                                    ]:
                                                        self.candles.append(f_candle)
                                            self.candles.sort(
                                                key=lambda x: self._parse_ts_to_int(
                                                    x.ts
                                                )
                                            )
                                        except Exception as be:
                                            pos_str = (
                                                self.broker.pos.side
                                                if self.broker.pos
                                                else "FLAT"
                                            )
                                            open_orders_count = len(
                                                getattr(
                                                    self.broker, "working_orders", []
                                                )
                                            )
                                            logger.exception(
                                                "Backfill failed",
                                                {
                                                    "event": "BackfillError",
                                                    "symbol": self.symbol,
                                                    "loop_id": self.loop_id,
                                                    "position": pos_str,
                                                    "open_orders_count": open_orders_count,
                                                    "interval": self.interval,
                                                    "error": str(be),
                                                },
                                            )
                        except Exception as ge:
                            pos_str = (
                                self.broker.pos.side if self.broker.pos else "FLAT"
                            )
                            open_orders_count = len(
                                getattr(self.broker, "working_orders", [])
                            )
                            logger.exception(
                                "Error checking for gaps",
                                {
                                    "event": "GapCheckError",
                                    "symbol": self.symbol,
                                    "loop_id": self.loop_id,
                                    "position": pos_str,
                                    "open_orders_count": open_orders_count,
                                    "interval": self.interval,
                                    "error": str(ge),
                                },
                            )

                        if not self.candles or item.ts != self.candles[-1].ts:
                            if self.candles:
                                await self.on_candle_closed(self.candles[-1])
                            self.candles.append(item)
                            if len(self.candles) > hard_limits.MAX_CANDLE_BUFFER:
                                self.candles = self.candles[
                                    -hard_limits.MAX_CANDLE_BUFFER :
                                ]
                        else:
                            self.candles[-1] = item

            except asyncio.CancelledError:
                break  # Exit cleanly on cancel
            except FatalError as fe:
                pos_str = self.broker.pos.side if self.broker.pos else "FLAT"
                open_orders_count = len(getattr(self.broker, "working_orders", []))
                logger.exception(
                    "FATAL_ERROR in market_data_task",
                    {
                        "event": "MarketDataFatal",
                        "symbol": self.symbol,
                        "loop_id": self.loop_id,
                        "position": pos_str,
                        "open_orders_count": open_orders_count,
                        "interval": self.interval,
                        "error": str(fe),
                    },
                )
                self.errors = MAX_ERRORS_PER_SESSION
                self._request_shutdown("fatal_error")
                break
            except Exception as e:
                # Item 1: Graceful restart instead of hard fail
                if self.shutdown_event.is_set():
                    break

                self.errors += 1
                self.consecutive_ws_errors += 1
                pos_str = self.broker.pos.side if self.broker.pos else "FLAT"
                open_orders_count = len(getattr(self.broker, "working_orders", []))
                logger.exception(
                    "Error in market data stream",
                    {
                        "event": "MarketDataError",
                        "symbol": self.symbol,
                        "loop_id": self.loop_id,
                        "position": pos_str,
                        "open_orders_count": open_orders_count,
                        "interval": self.interval,
                        "attempt": self.consecutive_ws_errors,
                        "error": str(e),
                    },
                )

                if self.consecutive_ws_errors >= 10:
                    if not self.shutdown_event.is_set():
                        logger.critical("Too many consecutive WS errors. Giving up.")
                        self._request_shutdown("market_data_errors")
                    break

                # Exponential backoff + jitter (cap at 60s)
                backoff = min(60.0, 2 ** min(self.consecutive_ws_errors, 6))
                jitter = random.uniform(0.0, 1.0)
                await asyncio.sleep(backoff + jitter)
            finally:
                if listener is not None:
                    try:
                        await listener.aclose()
                    except asyncio.CancelledError:
                        pass
                    except Exception as close_err:
                        pos_str = self.broker.pos.side if self.broker.pos else "FLAT"
                        open_orders_count = len(
                            getattr(self.broker, "working_orders", [])
                        )
                        logger.exception(
                            "Failed to close market data listener",
                            {
                                "event": "MarketDataListenerCloseError",
                                "symbol": self.symbol,
                                "loop_id": self.loop_id,
                                "position": pos_str,
                                "open_orders_count": open_orders_count,
                                "interval": self.interval,
                                "error": str(close_err),
                            },
                        )

    async def checkpoint_task(self):
        """Periodically saves state to disk for crash recovery."""
        try:
            while not self.shutdown_event.is_set():
                await asyncio.sleep(60)
                try:
                    # Item 13: Offload checkpointing to threads
                    def do_checkpoint():
                        self.state_manager.set_circuit_breaker_state(
                            self.circuit_breaker.get_status()
                        )
                        self.state_manager.set("starting_equity", self.starting_equity)
                        self.state_manager.save()
                        self.broker.save_state()

                    await asyncio.to_thread(do_checkpoint)
                    logger.info("Pulse checkpoint saved.")
                except Exception as e:
                    pos_str = self.broker.pos.side if self.broker.pos else "FLAT"
                    open_orders_count = len(getattr(self.broker, "working_orders", []))
                    logger.exception(
                        "Checkpoint failed",
                        {
                            "event": "CheckpointError",
                            "symbol": self.symbol,
                            "loop_id": self.loop_id,
                            "position": pos_str,
                            "open_orders_count": open_orders_count,
                            "interval": self.interval,
                            "error": str(e),
                        },
                    )
        except asyncio.CancelledError:
            pass

    async def kill_switch_task(self):
        """Monitors for kill.txt file to trigger emergency shutdown."""
        try:
            while not self.shutdown_event.is_set():
                if self.kill_file.exists() or os.getenv("LA_KILL_SWITCH") == "TRUE":
                    reason = (
                        "kill.txt detected"
                        if self.kill_file.exists()
                        else "LA_KILL_SWITCH=TRUE"
                    )
                    logger.warning(f"KILL SWITCH ACTIVATED: {reason}")
                    self._request_shutdown("kill_switch")
                    if self.kill_file.exists():
                        try:
                            self.kill_file.unlink()  # Remove file after processing
                        except Exception:
                            pass
                    # Special exit code for kill switch as requested in plan (though we are in async task)
                    # We'll set a flag to exit with 99 in the main block
                    self.kill_switch_triggered = True
                    break
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    async def stale_data_task(self):
        """Detects stale market data and triggers task restart or shutdown."""
        try:
            restart_threshold = min(30.0, self.stale_data_timeout_sec)
            while not self.shutdown_event.is_set():
                age = time.time() - self.last_data_time

                # Soft restart if data is hanging for more than 15 seconds
                # Soft restart if data is hanging for more than 15 seconds
                if age > 15.0:
                    logger.warning(f"STALE DATA: No market data for {age:.1f}s.")
                    # Attempt REST poll as a fallback signal when WS is unhealthy
                    now = time.time()
                    if now - self._last_rest_poll_time >= 15.0:
                        try:
                            from laptop_agents.data.loader import load_bitunix_candles

                            candles = await asyncio.to_thread(
                                load_bitunix_candles,
                                self.symbol,
                                self.interval,
                                2,
                            )
                            candles = normalize_candle_order(candles)
                            if candles:
                                latest = candles[-1]
                                latest_ts = self._parse_ts_to_int(latest.ts)
                                last_ts = (
                                    self._parse_ts_to_int(self.last_candle_ts)
                                    if self.last_candle_ts
                                    else 0
                                )
                                if latest_ts > last_ts:
                                    self.candles.append(latest)
                                    if (
                                        len(self.candles)
                                        > hard_limits.MAX_CANDLE_BUFFER
                                    ):
                                        self.candles = self.candles[
                                            -hard_limits.MAX_CANDLE_BUFFER :
                                        ]
                                    self.last_candle_ts = latest.ts
                                self.last_data_time = time.time()
                                self._last_rest_poll_time = now
                                logger.info(
                                    "REST_POLL_SUCCESS: refreshed candle from REST",
                                    {
                                        "event": "RestPollSuccess",
                                        "symbol": self.symbol,
                                        "loop_id": self.loop_id,
                                        "position": (
                                            self.broker.pos.side
                                            if self.broker.pos
                                            else "FLAT"
                                        ),
                                        "open_orders_count": len(
                                            getattr(self.broker, "working_orders", [])
                                        ),
                                        "interval": self.interval,
                                    },
                                )
                        except Exception as re:
                            logger.warning(f"REST poll failed during stale data: {re}")
                        finally:
                            self._last_rest_poll_time = now

                if age > restart_threshold:
                    if self.shutdown_event.is_set():
                        break  # Already shutting down
                    if self.stale_restart_attempts < self.max_stale_restarts:
                        self.stale_restart_attempts += 1
                        logger.error(
                            "STALE DATA: No market data for %.0fs. Attempting provider restart (%d/%d).",
                            age,
                            self.stale_restart_attempts,
                            self.max_stale_restarts,
                        )
                        append_event(
                            {
                                "event": "StaleDataRestart",
                                "error": f"no market data for {age:.0f}s",
                                "attempt": self.stale_restart_attempts,
                                "symbol": self.symbol,
                                "interval": self.interval,
                            },
                            paper=True,
                        )
                        try:
                            if self.provider and hasattr(self.provider, "client"):
                                self.provider.client.stop()
                                await asyncio.sleep(1.0)
                                self.provider.client.start()
                            elif (
                                self.provider
                                and hasattr(self.provider, "stop")
                                and hasattr(self.provider, "start")
                            ):
                                self.provider.stop()
                                await asyncio.sleep(1.0)
                                self.provider.start()
                            self.last_data_time = time.time()
                            self.consecutive_ws_errors = 0
                        except Exception as re:
                            logger.error(f"Provider restart failed: {re}")
                            self.errors += 1
                    elif age > self.stale_data_timeout_sec:
                        error_msg = (
                            f"STALE DATA: No market data for {age:.0f}s. "
                            "Restart attempts exhausted."
                        )
                        logger.error(error_msg)
                        self.errors += 1
                        # Ensure final report reflects this error
                        append_event(
                            {
                                "event": "StaleDataError",
                                "error": error_msg,
                                "symbol": self.symbol,
                                "interval": self.interval,
                            },
                            paper=True,
                        )
                        self._request_shutdown("stale_data")
                        break

                # Check data liveness
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass

    async def watchdog_tick_task(self):
        """Checks open positions against latest tick every 50ms (REALTIME SENTINEL)."""
        try:
            while not self.shutdown_event.is_set():
                if self.latest_tick and self.broker.pos:
                    # Item 4: Exception guard for watchdog logic
                    try:
                        events = self.broker.on_tick(self.latest_tick) or {}
                        for exit_event in events.get("exits", []):
                            self.trades += 1
                            logger.info(
                                f"REALTIME_TICK_EXIT: {exit_event['reason']} @ {exit_event['price']}"
                            )
                            self.metrics.append(
                                {
                                    "ts": datetime.now(timezone.utc).isoformat(),
                                    "elapsed": time.time() - self.start_time,
                                    "equity": self.broker.current_equity,
                                    "price": exit_event["price"],
                                    "unrealized": 0.0,
                                    "event": "REALTIME_TICK_EXIT",
                                    "reason": exit_event["reason"],
                                }
                            )
                            append_event(
                                {
                                    "event": "WatchdogExit",
                                    "tick": vars(self.latest_tick),
                                    **exit_event,
                                },
                                paper=True,
                            )
                    except Exception as e:
                        logger.error(f"Error in watchdog on_tick: {e}")
                        self.errors += 1
                        if self.errors >= MAX_ERRORS_PER_SESSION:
                            self._request_shutdown("error_budget")
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass

    async def on_candle_closed(self, candle: Candle):
        """Runs strategy logic when a candle is confirmed closed."""
        if math.isnan(candle.close) or candle.close <= 0:
            return
        self.iterations += 1
        warmup_bars = (
            self.strategy_config.get("warmup_bars", 50) if self.strategy_config else 50
        )

        # Item 11: Unified Warmup Guard
        if len(self.candles) < warmup_bars:
            if self.iterations % 10 == 0:
                logger.info(
                    f"WARMUP_IN_PROGRESS: {len(self.candles)}/{warmup_bars} bars"
                )
            return
        elif len(self.candles) == warmup_bars:
            logger.info("WARMUP_COMPLETE: Strategy active.")

        try:
            # Generate signal
            order = None

            if self.strategy_config:
                try:
                    # Use persistent supervisor and state for high performance
                    self.agent_state.candles = self.candles[:-1]
                    self.agent_state = self.supervisor.step(
                        self.agent_state, candle, skip_broker=True
                    )
                except Exception as agent_err:
                    pos_str = self.broker.pos.side if self.broker.pos else "FLAT"
                    open_orders_count = len(getattr(self.broker, "working_orders", []))
                    logger.exception(
                        "AGENT_ERROR: Strategy agent failed, skipping signal",
                        {
                            "event": "AgentError",
                            "symbol": self.symbol,
                            "loop_id": self.loop_id,
                            "position": pos_str,
                            "open_orders_count": open_orders_count,
                            "interval": self.interval,
                            "error": str(agent_err),
                        },
                    )
                    append_event(
                        {"event": "AgentError", "error": str(agent_err)}, paper=True
                    )
                    self.errors += 1
                    return

            agent_order = self.agent_state.order if self.strategy_config else {}
            if (
                self.kill_switch_triggered
                or self.shutdown_event.is_set()
                or self.circuit_breaker.is_tripped()
            ):
                agent_order = {}
            if agent_order and agent_order.get("go"):

                def safe_float(value: Any, default: float) -> float:
                    try:
                        if value is None:
                            return float(default)
                        return float(value)
                    except (TypeError, ValueError):
                        return float(default)

                entry = safe_float(agent_order.get("entry"), candle.close)
                qty = safe_float(agent_order.get("qty"), 0.0)
                sl = safe_float(agent_order.get("sl"), 0.0)
                tp = safe_float(agent_order.get("tp"), 0.0)
                order_symbol = agent_order.get("symbol") or self.symbol

                if order_symbol != self.symbol:
                    logger.warning("ORDER_REJECTED: Symbol mismatch")
                    append_event(
                        {
                            "event": "OrderRejected",
                            "reason": "symbol_mismatch",
                            "symbol": order_symbol,
                            "expected_symbol": self.symbol,
                        },
                        paper=True,
                    )
                    order = None
                else:
                    order = {
                        "go": True,
                        "side": agent_order.get("side"),
                        "symbol": order_symbol,
                        "entry_type": agent_order.get("entry_type", "market"),
                        "entry": entry,
                        "qty": qty,
                        "sl": sl,
                        "tp": tp,
                        "equity": self.broker.current_equity,
                        "client_order_id": f"async_{uuid.uuid4().hex}",
                    }

                    if order["side"] not in {"LONG", "SHORT"}:
                        logger.warning("ORDER_REJECTED: Invalid side")
                        order = None
                    elif order["sl"] <= 0 or order["tp"] <= 0:
                        logger.warning("ORDER_REJECTED: Non-positive SL/TP")
                        order = None
                    elif not all(
                        math.isfinite(x)
                        for x in [
                            order["entry"],
                            order["qty"],
                            order["sl"],
                            order["tp"],
                        ]
                    ):
                        logger.warning("ORDER_REJECTED: Non-finite order fields")
                        order = None
                    elif order["qty"] <= 0:
                        logger.warning("ORDER_REJECTED: Non-positive quantity")
                        order = None
                    else:
                        if order["side"] == "LONG":
                            if not (order["sl"] < order["entry"] < order["tp"]):
                                logger.warning(
                                    "ORDER_REJECTED: Invalid LONG SL/TP ordering"
                                )
                                order = None
                        elif order["side"] == "SHORT":
                            if not (order["tp"] < order["entry"] < order["sl"]):
                                logger.warning(
                                    "ORDER_REJECTED: Invalid SHORT SL/TP ordering"
                                )
                                order = None

            # Queue order for async execution (non-blocking)
            if order and order.get("go"):
                latency_ms = random.randint(50, 500)
                logger.info(f"Queuing order for execution (latency: {latency_ms}ms)")
                try:
                    self.execution_queue.put_nowait(
                        {
                            "order": order,
                            "candle": candle,
                            "latency_ms": latency_ms,
                            "queued_at": time.time(),
                        }
                    )
                except asyncio.QueueFull:
                    logger.error("EXECUTION_QUEUE_FULL: Order dropped!")
                    append_event(
                        {"event": "OrderDropped", "reason": "queue_full"}, paper=True
                    )
                    self.errors += 1
                    if (
                        self.errors >= MAX_ERRORS_PER_SESSION
                        and not self.shutdown_event.is_set()
                    ):
                        logger.error(
                            f"ERROR BUDGET EXHAUSTED: {self.errors} errors. Shutting down."
                        )
                        self._request_shutdown("error_budget")
            else:
                # Still process candle for exits on existing positions
                events = self.broker.on_candle(candle, None, tick=self.latest_tick)
                for exit_event in events.get("exits", []):
                    self.trades += 1
                    logger.info(
                        f"CANDLE EXIT: {exit_event['reason']} @ {exit_event['price']}"
                    )
                    append_event({"event": "CandleExit", **exit_event}, paper=True)
                    self.circuit_breaker.update_equity(
                        self.broker.current_equity, exit_event.get("pnl", 0)
                    )

        except Exception as e:
            logger.exception(f"Error in on_candle_closed: {e}")
            self.errors += 1
            if (
                self.errors >= MAX_ERRORS_PER_SESSION
                and not self.shutdown_event.is_set()
            ):
                logger.error(
                    f"ERROR BUDGET EXHAUSTED: {self.errors} errors. Shutting down."
                )
                self._request_shutdown("error_budget")

    async def heartbeat_task(self):
        """Logs system status every second."""
        import time as time_module

        heartbeat_path = Path("logs/heartbeat.json")
        heartbeat_path.parent.mkdir(exist_ok=True)

        try:
            while not self.shutdown_event.is_set():
                try:
                    elapsed = time.time() - self.start_time
                    pos_str = self.broker.pos.side if self.broker.pos else "FLAT"
                    open_orders_count = len(getattr(self.broker, "working_orders", []))
                    price = (
                        self.latest_tick.last
                        if self.latest_tick
                        else (self.candles[-1].close if self.candles else 0.0)
                    )

                    unrealized = self.broker.get_unrealized_pnl(price)
                    total_equity = self.broker.current_equity + unrealized

                    # Update max drawdown tracking
                    self.max_equity = max(self.max_equity, total_equity)
                    dd = (
                        (self.max_equity - total_equity) / self.max_equity
                        if self.max_equity > 0
                        else 0
                    )
                    self.max_drawdown = max(self.max_drawdown, dd)

                    max_loss_usd = hard_limits.MAX_DAILY_LOSS_USD
                    drawdown_usd = self.starting_equity - total_equity
                    if (
                        self.starting_equity > 0
                        and drawdown_usd >= max_loss_usd
                        and not self.kill_switch_triggered
                    ):
                        logger.critical(
                            "RISK KILL SWITCH TRIPPED",
                            {
                                "event": "RiskKillSwitch",
                                "symbol": self.symbol,
                                "loop_id": self.loop_id,
                                "position": pos_str,
                                "open_orders_count": open_orders_count,
                                "equity": total_equity,
                                "drawdown_usd": drawdown_usd,
                                "limit_usd": max_loss_usd,
                            },
                        )
                        append_event(
                            {
                                "event": "RiskKillSwitch",
                                "symbol": self.symbol,
                                "loop_id": self.loop_id,
                                "position": pos_str,
                                "open_orders_count": open_orders_count,
                                "equity": total_equity,
                                "drawdown_usd": drawdown_usd,
                                "limit_usd": max_loss_usd,
                            },
                            paper=True,
                        )
                        self.kill_switch_triggered = True
                        self._request_shutdown("max_loss_usd")
                        try:
                            self.broker.cancel_all_open_orders()
                            if price and price > 0:
                                self.broker.close_all(price)
                        except Exception as e:
                            logger.exception(
                                "Risk kill switch cleanup failed",
                                {
                                    "event": "RiskKillSwitchCleanupError",
                                    "symbol": self.symbol,
                                    "loop_id": self.loop_id,
                                    "position": pos_str,
                                    "open_orders_count": open_orders_count,
                                    "interval": self.interval,
                                    "error": str(e),
                                },
                            )

                    process = psutil.Process()
                    mem_mb = process.memory_info().rss / 1024 / 1024
                    cpu_pct = process.cpu_percent()

                    # Phase 4.1: Memory Tuning from Env
                    max_mem_allowed = float(os.getenv("LA_MAX_MEMORY_MB", "1500"))

                    if mem_mb > max_mem_allowed:
                        logger.critical(
                            f"CRITICAL: Memory Limit ({mem_mb:.1f}MB > {max_mem_allowed}MB). Shutting down."
                        )
                        self._request_shutdown("memory_limit")

                    # Save last price cache
                    if self.latest_tick:
                        try:
                            price_cache_path = Path("paper/last_price_cache.json")
                            price_cache_path.parent.mkdir(exist_ok=True)
                            with open(price_cache_path, "w") as f:
                                json.dump(
                                    {
                                        "last": self.latest_tick.last,
                                        "ts": self.latest_tick.ts,
                                    },
                                    f,
                                )
                        except Exception:
                            pass

                    # Write heartbeat file for watchdog
                    with heartbeat_path.open("w") as f:
                        json.dump(
                            {
                                "ts": datetime.now(timezone.utc).isoformat(),
                                "unix_ts": time_module.time(),
                                "last_updated_ts": time_module.time(),
                                "elapsed": elapsed,
                                "equity": total_equity,
                                "symbol": self.symbol,
                                "ram_mb": round(mem_mb, 2),
                                "cpu_pct": cpu_pct,
                            },
                            f,
                        )

                    remaining = max(
                        0, (self.start_time + (self.duration_min * 60)) - time.time()
                    )
                    remaining_str = f"{int(remaining // 60)}:{int(remaining % 60):02d}"

                    logger.info(
                        f"[ASYNC] {self.symbol} | Price: {price:,.2f} | Pos: {pos_str:5} | "
                        f"Equity: ${total_equity:,.2f} | "
                        f"Elapsed: {elapsed:.0f}s | Remaining: {remaining_str}",
                        {
                            "event": "Heartbeat",
                            "symbol": self.symbol,
                            "loop_id": self.loop_id,
                            "position": pos_str,
                            "open_orders_count": open_orders_count,
                        },
                    )

                    append_event(
                        {
                            "event": "AsyncHeartbeat",
                            "symbol": self.symbol,
                            "loop_id": self.loop_id,
                            "position": pos_str,
                            "open_orders_count": open_orders_count,
                            "price": price,
                            "equity": total_equity,
                            "unrealized": unrealized,
                            "elapsed": elapsed,
                        },
                        paper=True,
                    )

                    # Collect metric data point
                    self.metrics.append(
                        {
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "elapsed": elapsed,
                            "equity": total_equity,
                            "price": price,
                            "unrealized": unrealized,
                            "errors": self.errors,
                        }
                    )

                    self.last_heartbeat_time = time.time()
                except Exception as e:
                    logger.exception(f"Heartbeat task error: {e}")
                    self.errors += 1
                    pos_str = self.broker.pos.side if self.broker.pos else "FLAT"
                    open_orders_count = len(getattr(self.broker, "working_orders", []))
                    append_event(
                        {
                            "event": "HeartbeatTaskError",
                            "error": str(e),
                            "symbol": self.symbol,
                            "loop_id": self.loop_id,
                            "position": pos_str,
                            "open_orders_count": open_orders_count,
                            "interval": self.interval,
                        },
                        paper=True,
                    )
                    if (
                        self.errors >= MAX_ERRORS_PER_SESSION
                        and not self.shutdown_event.is_set()
                    ):
                        self._request_shutdown("error_budget")
                await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            pass

    async def timer_task(self, end_time: float):
        """Triggers shutdown after duration_limit."""
        try:
            while time.time() < end_time:
                await asyncio.sleep(1.0)
            logger.info("Duration limit reached. Shutting down...")
            self._request_shutdown("duration_limit")
        except asyncio.CancelledError:
            pass

    async def funding_task(self):
        """Checks for 8-hour funding windows (00:00, 08:00, 16:00 UTC)."""
        # Initialize last_funding_hour to current hour to avoid instant charge on startup if within window
        now = datetime.now(timezone.utc)
        last_funding_hour = now.hour if now.minute == 0 else None

        try:
            while not self.shutdown_event.is_set():
                now = datetime.now(timezone.utc)
                # Funding windows: 00:00, 08:00, 16:00 UTC
                if (
                    now.hour in [0, 8, 16]
                    and now.minute == 0
                    and now.hour != last_funding_hour
                ):
                    logger.info(f"Funding window detected at {now.hour:02d}:00 UTC")
                    if (
                        self.provider
                        and hasattr(self.provider, "funding_rate")
                        and asyncio.iscoroutinefunction(self.provider.funding_rate)
                    ):
                        try:
                            rate = await self.provider.funding_rate()
                            logger.info(f"FUNDING APPLIED: Rate {rate:.6f}")
                            self.broker.apply_funding(rate, now.isoformat())
                        except Exception as fe:
                            logger.warning(f"Failed to fetch/apply funding rate: {fe}")
                    else:
                        logger.debug(
                            "Provider does not support funding_rate(). Skipping."
                        )
                    last_funding_hour = now.hour

                if now.minute != 0:
                    last_funding_hour = None

                await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass

    async def execution_task(self):
        """Consumes orders from execution_queue and processes them with simulated latency."""
        try:
            while not self.shutdown_event.is_set():
                try:
                    # Wait for an order with timeout so we can check shutdown
                    order_payload = await asyncio.wait_for(
                        self.execution_queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                if self.kill_switch_triggered:
                    continue

                client_order_id = None
                try:
                    order = order_payload.get("order")
                    candle = order_payload.get("candle")

                    if not order or not order.get("go"):
                        continue

                    # Item 8: Immediate ID locking
                    client_order_id = order.get("client_order_id")
                    if client_order_id:
                        if client_order_id in self._inflight_order_ids:
                            logger.warning(
                                f"Duplicate order {client_order_id} detected. Skipping."
                            )
                            continue
                        self._inflight_order_ids.add(client_order_id)

                    # Simulate network latency WITHOUT blocking main loop
                    if not self.dry_run:
                        latency = order_payload.get("latency_ms", 200)
                        logger.debug(
                            f"Executing order with {latency}ms simulated latency"
                        )
                        await asyncio.sleep(latency / 1000.0)

                    # Get the CURRENT tick after latency (realistic fill price)
                    current_tick = self.latest_tick

                    # Execute via broker
                    events = self.broker.on_candle(candle, order, tick=current_tick)

                    for fill in events.get("fills", []):
                        self.trades += 1
                        logger.info(f"EXECUTION FILL: {fill['side']} @ {fill['price']}")
                        append_event({"event": "ExecutionFill", **fill}, paper=True)

                    for exit_event in events.get("exits", []):
                        self.trades += 1
                        logger.info(
                            f"EXECUTION EXIT: {exit_event['reason']} @ {exit_event['price']}"
                        )
                        append_event(
                            {"event": "ExecutionExit", **exit_event}, paper=True
                        )

                    # Update circuit breaker
                    trade_pnl = None
                    for exit_event in events.get("exits", []):
                        trade_pnl = exit_event.get("pnl", 0)

                    self.circuit_breaker.update_equity(
                        self.broker.current_equity, trade_pnl
                    )

                    if self.circuit_breaker.is_tripped():
                        logger.warning(
                            f"CIRCUIT BREAKER TRIPPED: {self.circuit_breaker.get_status()}"
                        )
                        self._request_shutdown("circuit_breaker_tripped")

                    # Save state
                    if not self.dry_run:
                        self.state_manager.set_circuit_breaker_state(
                            self.circuit_breaker.get_status()
                        )
                        self.state_manager.save()
                except Exception as e:
                    logger.exception(f"Execution task error: {e}")
                    self.errors += 1
                    pos_str = self.broker.pos.side if self.broker.pos else "FLAT"
                    open_orders_count = len(getattr(self.broker, "working_orders", []))
                    append_event(
                        {
                            "event": "ExecutionTaskError",
                            "error": str(e),
                            "symbol": self.symbol,
                            "loop_id": self.loop_id,
                            "position": pos_str,
                            "open_orders_count": open_orders_count,
                            "interval": self.interval,
                        },
                        paper=True,
                    )
                    if (
                        self.errors >= MAX_ERRORS_PER_SESSION
                        and not self.shutdown_event.is_set()
                    ):
                        self._request_shutdown("error_budget")
                finally:
                    if client_order_id:
                        self._inflight_order_ids.discard(client_order_id)

        except asyncio.CancelledError:
            pass

    def _threaded_watchdog(self):
        """Independent thread that kills the process if main loop freezes."""
        process = psutil.Process()
        while not self.shutdown_event.is_set():
            if self.shutdown_event.is_set():
                break
            age = time.time() - self.last_heartbeat_time
            # Item 14: Increased threshold and graceful attempt
            if age > 60:
                print(
                    f"\n\n!!! WATCHDOG FATAL: Main loop frozen for {age:.1f}s. !!!\n\n"
                )
                logger.critical(f"WATCHDOG_FATAL: Main loop frozen for {age:.1f}s.")
                self._request_shutdown("watchdog_frozen")
                time.sleep(5)  # Give it 5s to shut down gracefully
                os._exit(1)

            # Memory check (Phase 4.1)
            try:
                mem_rss_mb = process.memory_info().rss / 1024 / 1024
                # Use LA_MAX_MEMORY_MB for hardware watchdog as well
                max_mem_allowed = float(os.getenv("LA_MAX_MEMORY_MB", "1500"))
                if mem_rss_mb > max_mem_allowed:
                    print(
                        f"\n\n!!! CRITICAL: Memory Limit Exceeded ({mem_rss_mb:.1f} MB). FORCE EXITing. !!!\n\n"
                    )
                    logger.critical(
                        f"CRITICAL: Memory Limit Exceeded ({mem_rss_mb:.1f} MB). RSS > {max_mem_allowed} MB."
                    )
                    self._request_shutdown("memory_limit")
                    os._exit(1)
            except Exception:
                pass

            time.sleep(1)


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
) -> AsyncSessionResult:
    """Entry point for the async session."""

    # Task 3: Startup Safety - PID Locking
    lock_path = Path("paper/async_session.lock")
    lock_path.parent.mkdir(exist_ok=True)
    try:
        # atomic 'x' mode (fails if file exists)
        with open(lock_path, "x") as f:
            f.write(str(os.getpid()))
    except FileExistsError:
        try:
            existing_pid = None
            with open(lock_path, "r") as f:
                pid_str = f.read().strip()
                if pid_str.isdigit():
                    existing_pid = int(pid_str)
            if existing_pid and not psutil.pid_exists(existing_pid):
                lock_path.unlink(missing_ok=True)
                with open(lock_path, "x") as f:
                    f.write(str(os.getpid()))
            else:
                logger.error(
                    "Session already running (lock file exists: paper/async_session.lock)"
                )
                # Return a result indicating it didn't run
                return AsyncSessionResult(stopped_reason="already_running")
        except Exception as e:
            logger.error(f"Failed to validate existing lock file: {e}")
            return AsyncSessionResult(stopped_reason="already_running")
    except Exception as e:
        logger.warning(f"Could not create PID lock file: {e}")

    # Reference Persistence: Restore starting_equity from local state if available
    unified_state_path = Path("paper/unified_state.json")
    if unified_state_path.exists():
        try:
            with open(unified_state_path, "r") as f:
                state = json.load(f)
                restored_equity = state.get("starting_equity")
                if restored_equity:
                    logger.info(
                        f"RECOVERY: Restored starting_equity from state: ${restored_equity:,.2f}"
                    )
                    starting_balance = float(restored_equity)
        except Exception as e:
            logger.warning(f"Failed to restore starting_equity from state: {e}")

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
        )

        # Determine Provider based on config/path
        if replay_path:
            from laptop_agents.backtest.replay_runner import ReplayProvider

            runner.provider = ReplayProvider(Path(replay_path))
            logger.info(f"Using REPLAY PROVIDER from {replay_path}")
        elif strategy_config and strategy_config.get("source") == "mock":
            from laptop_agents.data.providers.mock import MockProvider

            runner.provider = MockProvider()
            logger.info("Using MOCK PROVIDER (simulated market data)")

        if runner.provider is None:
            from laptop_agents.data.providers.bitunix_ws import BitunixWSProvider

            runner.provider = BitunixWSProvider(symbol)
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
        try:
            LATEST_DIR.mkdir(parents=True, exist_ok=True)
            summary = {
                "run_id": f"async_{int(runner.start_time)}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "bitunix",
                "symbol": symbol,
                "interval": interval,
                "candle_count": len(runner.candles),
                "last_ts": runner.candles[-1].ts if runner.candles else "",
                "last_close": (
                    float(runner.candles[-1].close) if runner.candles else 0.0
                ),
                "fees_bps": fees_bps,
                "slip_bps": slip_bps,
                "starting_balance": starting_balance,
                "ending_balance": runner.broker.current_equity,
                "net_pnl": runner.broker.current_equity - starting_balance,
                "max_drawdown": runner.max_drawdown,
                "trades": runner.trades,
                "mode": "async",
            }
            # Pass trades from broker history for a complete report
            trades_for_report = [
                h for h in runner.broker.order_history if h.get("type") == "exit"
            ]
            render_html(
                summary,
                trades_for_report,
                "",
                candles=runner.candles,
            )
            logger.info(f"HTML report generated at {LATEST_DIR / 'summary.html'}")
        except Exception as e:
            logger.error(f"Failed to generate HTML report: {e}")

    except Exception as top_e:
        logger.error(f"Fatal error in async session setup: {top_e}")
    finally:
        # Cleanup PID lock
        if lock_path.exists():
            try:
                lock_path.unlink()
            except Exception:
                pass

    if runner:
        return AsyncSessionResult(
            iterations=runner.iterations,
            trades=runner.trades,
            errors=runner.errors,
            starting_equity=runner.starting_equity,
            ending_equity=runner.broker.current_equity,
            duration_sec=time.time() - runner.start_time,
            max_drawdown=runner.max_drawdown,
            stopped_reason=runner.stopped_reason,
        )
    else:
        return AsyncSessionResult(stopped_reason="init_failed")
