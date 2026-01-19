from __future__ import annotations

import asyncio
import json
import random
import signal
import time
import threading
import os
import psutil
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
        stale_timeout: int = 30,
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
        self.kill_file = REPO_ROOT / "kill.txt"
        self.kill_switch_triggered = False
        self.execution_latency_ms = execution_latency_ms
        self.status = "initializing"
        self._shutting_down = False
        self._last_backfill_time = 0.0
        self.max_equity = starting_balance
        self.max_drawdown = 0.0

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

        try:
            await self.shutdown_event.wait()
        finally:
            self.status = "shutting_down"
            logger.info("GRACEFUL SHUTDOWN INITIATED")

            # 1. Set shutting down flag
            self._shutting_down = True

            # 2. Cancel all open orders (alias in PaperBroker)
            try:
                self.broker.cancel_all_open_orders()
            except Exception as e:
                logger.error(f"Failed to cancel orders: {e}")

            # 3. Wait up to 5s for pending fills (non-blocking sleep in finally)
            # Since we are in finally, we can't easily wait for more tasks if they are cancelled,
            # but we can do a quick async sleep if the loop is still alive.
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
                        if hasattr(self.broker, "working_orders"):
                            self.broker.working_orders.append(order)  # type: ignore
                        logger.info(
                            f"Drained pending order {order.get('client_order_id')} to broker state"
                        )
                except asyncio.QueueEmpty:
                    break

            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

            # Final cleanup
            if self.broker.pos and self.latest_tick:
                self.broker.close_all(self.latest_tick.last)

            try:
                await asyncio.wait_for(
                    asyncio.shield(asyncio.to_thread(self.broker.shutdown)), timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning("Broker shutdown timed out after 5s")
            except Exception as e:
                logger.exception(f"Broker shutdown failed: {e}")

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

    async def market_data_task(self):
        """Consumes WebSocket data and triggers strategy on candle closure."""
        while not self.shutdown_event.is_set():
            try:
                # Re-enter the listener if it yields (it handles its own inner logic but this catches generator exit)
                async for item in self.provider.listen():
                    if self.shutdown_event.is_set():
                        break

                    # Reset timeout timer on each successful item (Item 1)
                    self.last_data_time = time.time()

                    if isinstance(item, DataEvent):
                        logger.warning(
                            f"RECEIVED_DATA_EVENT: {item.event} | {item.details}"
                        )
                        if (
                            item.event == "ORDER_BOOK_STALE"
                            or item.event == "CIRCUIT_TRIPPED"
                        ):
                            # Critical failures that might warrant restart or shutdown
                            # For now, we trust the provider's circuit breaker to have tried enough
                            write_alert(f"MARKET_DATA_FAILED: {item.event}")
                            # We could try to reconstruct the provider here, but shutdown is safer if CB tripped
                            self.shutdown_event.set()
                            break

                    if isinstance(item, Tick):
                        # Robust Validation
                        if (
                            item.last <= 0
                            or item.ask <= 0
                            or math.isnan(item.last)
                            or math.isinf(item.last)
                        ):
                            logger.warning(
                                "INVALID_TICK: Non-positive or NaN/Inf price. Skipping."
                            )
                            continue

                        ts_sec = self._parse_ts_to_int(item.ts)
                        if ts_sec < 1704067200:  # Before 2024
                            logger.warning(
                                f"INVALID_TIMESTAMP: Tick {item.ts} is too old or malformed. Skipping."
                            )
                            continue

                        self.latest_tick = item
                        if self.consecutive_ws_errors > 0:
                            logger.info("WS connection recovered. Error count reset.")
                            self.consecutive_ws_errors = 0

                    elif isinstance(item, Candle):
                        # Robust Validation
                        if (
                            item.close <= 0
                            or item.open <= 0
                            or math.isnan(item.close)
                            or math.isinf(item.close)
                        ):
                            logger.warning(
                                "INVALID_CANDLE: Non-positive or NaN/Inf price. Skipping."
                            )
                            continue

                        new_ts_sec = self._parse_ts_to_int(item.ts)
                        if new_ts_sec < 1704067200:
                            logger.warning(
                                f"INVALID_TIMESTAMP: Candle {item.ts} is too old or malformed. Skipping."
                            )
                            continue

                        # Gap Backfill Logic
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
                                    if missing_count > 0:
                                        # Rate limit backfills to max 1 per 30 seconds
                                        now = time.time()
                                        if now - self._last_backfill_time < 30.0:
                                            logger.debug(
                                                "Skipping backfill: rate limited "
                                                f"({now - self._last_backfill_time:.1f}s since last)"
                                            )
                                        else:
                                            logger.warning(
                                                f"GAP_DETECTED: {missing_count} missing candles. "
                                                "Attempting async backfill..."
                                            )
                                            self._last_backfill_time = now
                                            # Use asyncio.to_thread to avoid blocking main loop (Item 5)
                                        try:
                                            fetched = await asyncio.to_thread(
                                                load_bitunix_candles,
                                                self.symbol,
                                                self.interval,
                                                min(missing_count + 5, 200),
                                            )

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
                                                        logger.info(
                                                            f"Injected missing candle: {f_candle.ts}"
                                                        )
                                            self.candles.sort(
                                                key=lambda x: self._parse_ts_to_int(
                                                    x.ts
                                                )
                                            )
                                        except Exception as be:
                                            logger.error(f"Backfill failed: {be}")
                        except (ValueError, TypeError, AttributeError, Exception) as ge:
                            logger.error(f"Error checking for gaps: {ge}")

                        # Check if this is a NEW candle or an update to the current one
                        if not self.candles or item.ts != self.candles[-1].ts:
                            # New candle! This means the previous one just closed.
                            if self.candles:
                                closed_candle = self.candles[-1]
                                await self.on_candle_closed(closed_candle)

                            self.candles.append(item)
                            # Phase 4.3: Strict Candle Buffer Cap
                            if len(self.candles) > hard_limits.MAX_CANDLE_BUFFER:
                                self.candles = self.candles[
                                    -hard_limits.MAX_CANDLE_BUFFER :
                                ]
                        else:
                            # Update current open candle
                            self.candles[-1] = item

            except asyncio.CancelledError:
                break  # Exit cleanly on cancel
            except FatalError as fe:
                logger.error(f"FATAL_ERROR in market_data_task: {fe}")
                self.errors = MAX_ERRORS_PER_SESSION
                self.shutdown_event.set()
                break
            except Exception as e:
                # Item 1: Graceful restart instead of hard fail
                if self.shutdown_event.is_set():
                    break

                self.errors += 1
                self.consecutive_ws_errors += 1
                logger.exception(
                    f"Error in market data stream (attempt {self.consecutive_ws_errors}): {e}"
                )

                if self.consecutive_ws_errors >= 10:
                    if not self.shutdown_event.is_set():
                        logger.critical("Too many consecutive WS errors. Giving up.")
                        self.shutdown_event.set()
                    break

                # Wait a bit before retrying the loop
                await asyncio.sleep(5.0)

    async def checkpoint_task(self):
        """Periodically saves state to disk for crash recovery."""
        try:
            while not self.shutdown_event.is_set():
                await asyncio.sleep(60)
                logger.info("Pulse Checkpointing: Saving system state...")
                try:
                    self.state_manager.set_circuit_breaker_state(
                        self.circuit_breaker.get_status()
                    )
                    self.state_manager.set("starting_equity", self.starting_equity)
                    self.state_manager.save()
                    self.broker.save_state()
                except Exception as e:
                    logger.error(f"Checkpoint failed: {e}")
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
                    self.shutdown_event.set()
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
            while not self.shutdown_event.is_set():
                age = time.time() - self.last_data_time

                # Soft restart if data is hanging for more than 15 seconds
                # Soft restart if data is hanging for more than 15 seconds
                if age > 15.0 and self.consecutive_ws_errors == 0:
                    logger.warning(f"STALE DATA: No market data for {age:.1f}s.")
                    # We can't easily restart just the task without refactoring, so we treat it as an early warning.
                    # If it persists to stale_data_timeout_sec, we shut down.

                if age > self.stale_data_timeout_sec:
                    if self.shutdown_event.is_set():
                        break  # Already shutting down
                    error_msg = f"STALE DATA: No market data for {age:.0f}s. Triggering session restart."
                    logger.error(error_msg)
                    self.errors += 1
                    # Ensure final report reflects this error
                    append_event(
                        {"event": "StaleDataError", "error": error_msg}, paper=True
                    )
                    self.shutdown_event.set()
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
                    try:
                        events = self.broker.on_tick(self.latest_tick)
                        for exit_event in events.get("exits", []):
                            self.trades += 1
                            logger.info(
                                f"REALTIME_TICK_EXIT: {exit_event['reason']} @ {exit_event['price']}"
                            )

                            # Phase 1: Update metrics immediately on realtime exit
                            elapsed = time.time() - self.start_time
                            self.metrics.append(
                                {
                                    "ts": datetime.now(timezone.utc).isoformat(),
                                    "elapsed": elapsed,
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

                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass

    async def on_candle_closed(self, candle: Candle):
        """Runs strategy logic when a candle is confirmed closed."""
        self.iterations += 1
        logger.info(f"Candle closed: {candle.ts} at {candle.close}")

        # Early exit if insufficient history
        if len(self.candles) < 2:
            logger.debug("Skipping strategy: insufficient candle history (<2)")
            return

        if hasattr(candle, "volume") and float(candle.volume) == 0:
            logger.warning(f"LOW_VOLUME_WARNING: Candle {candle.ts} has zero volume")

        if self.circuit_breaker.is_tripped():
            logger.warning("SIGNAL BLOCKED: Circuit breaker is tripped.")
            return

        # 4.2 Warmup Period (No-Trade Zone)
        warmup_bars = 50
        if self.strategy_config:
            warmup_bars = self.strategy_config.get("warmup_bars", 50)

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
            raw_signal = None

            if self.strategy_config:
                try:
                    # Use persistent supervisor and state for high performance
                    self.agent_state.candles = self.candles[:-1]
                    self.agent_state = self.supervisor.step(
                        self.agent_state, candle, skip_broker=True
                    )

                    if self.agent_state.setup.get("side") in ["LONG", "SHORT"]:
                        raw_signal = (
                            "BUY"
                            if self.agent_state.setup["side"] == "LONG"
                            else "SELL"
                        )
                except Exception as agent_err:
                    logger.error(
                        f"AGENT_ERROR: Strategy agent failed, skipping signal: {agent_err}"
                    )
                    append_event(
                        {"event": "AgentError", "error": str(agent_err)}, paper=True
                    )
                    raw_signal = None  # Suppress trade on agent failure

            if raw_signal:
                signal_side = "LONG" if raw_signal == "BUY" else "SHORT"
                risk_amount = self.broker.current_equity * (self.risk_pct / 100.0)
                stop_distance = float(candle.close) * (self.stop_bps / 10000.0)

                if stop_distance > 0:
                    qty = risk_amount / stop_distance
                    order = {
                        "go": True,
                        "side": signal_side,
                        "entry_type": "market",
                        "entry": float(candle.close),
                        "qty": qty,
                        "sl": (
                            float(candle.close) - stop_distance
                            if signal_side == "LONG"
                            else float(candle.close) + stop_distance
                        ),
                        "tp": (
                            float(candle.close) + (stop_distance * self.tp_r)
                            if signal_side == "LONG"
                            else float(candle.close) - (stop_distance * self.tp_r)
                        ),
                        "equity": self.broker.current_equity,
                        "client_order_id": f"async_{int(time.time())}_{self.iterations}",
                    }

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
                self.shutdown_event.set()

    async def heartbeat_task(self):
        """Logs system status every second."""
        import time as time_module

        heartbeat_path = Path("logs/heartbeat.json")
        heartbeat_path.parent.mkdir(exist_ok=True)

        try:
            while not self.shutdown_event.is_set():
                elapsed = time.time() - self.start_time
                pos_str = self.broker.pos.side if self.broker.pos else "FLAT"
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

                process = psutil.Process()
                mem_mb = process.memory_info().rss / 1024 / 1024
                cpu_pct = process.cpu_percent()

                # Phase 4.1: Memory Tuning from Env
                max_mem_allowed = float(os.getenv("LA_MAX_MEMORY_MB", "1500"))

                if mem_mb > max_mem_allowed:
                    logger.critical(
                        f"CRITICAL: Memory Limit ({mem_mb:.1f}MB > {max_mem_allowed}MB). Shutting down."
                    )
                    self.shutdown_event.set()

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
                    f"Elapsed: {elapsed:.0f}s | Remaining: {remaining_str}"
                )

                append_event(
                    {
                        "event": "AsyncHeartbeat",
                        "price": price,
                        "pos": pos_str,
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
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            pass

    async def timer_task(self, end_time: float):
        """Triggers shutdown after duration_limit."""
        try:
            while time.time() < end_time:
                await asyncio.sleep(1.0)
            logger.info("Duration limit reached. Shutting down...")
            self.shutdown_event.set()
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
                    if hasattr(self.provider, "funding_rate") and callable(
                        self.provider.funding_rate
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

                order = order_payload.get("order")
                candle = order_payload.get("candle")

                if not order or not order.get("go"):
                    continue

                # Add idempotency check
                client_order_id = order.get("client_order_id")
                if client_order_id and hasattr(self.broker, "processed_order_ids"):
                    if client_order_id in self.broker.processed_order_ids:
                        logger.warning(
                            f"Duplicate order {client_order_id} in execution queue. Skipping."
                        )
                        continue

                # Simulate network latency WITHOUT blocking main loop
                if not self.dry_run:
                    latency = order_payload.get("latency_ms", 200)
                    logger.debug(f"Executing order with {latency}ms simulated latency")
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
                    append_event({"event": "ExecutionExit", **exit_event}, paper=True)

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
                    self.shutdown_event.set()

                # Save state
                if not self.dry_run:
                    self.state_manager.set_circuit_breaker_state(
                        self.circuit_breaker.get_status()
                    )
                    self.state_manager.save()

        except asyncio.CancelledError:
            pass

    def _threaded_watchdog(self):
        """Independent thread that kills the process if main loop freezes."""
        process = psutil.Process()
        while not self.shutdown_event.is_set():
            # Heartbeat check
            age = time.time() - self.last_heartbeat_time
            if age > 30:
                # Use critical print as logger might be stuck too
                print(
                    f"\n\n!!! WATCHDOG FATAL: Main loop frozen for {age:.1f}s. FORCE EXITing. !!!\n\n"
                )
                logger.critical(
                    f"WATCHDOG_FATAL: Main loop frozen for {age:.1f}s. HARD EXIT."
                )
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
    stale_timeout: int = 30,
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
        logger.error(
            "Session already running (lock file exists: paper/async_session.lock)"
        )
        # Return a result indicating it didn't run
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
                runner.shutdown_event.set()

        try:
            loop = asyncio.get_running_loop()
            if os.name != "nt":
                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.add_signal_handler(sig, runner.shutdown_event.set)
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
            runner.shutdown_event.set()
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
        )
    else:
        return AsyncSessionResult(stopped_reason="init_failed")
