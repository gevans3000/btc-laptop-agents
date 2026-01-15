from __future__ import annotations

import asyncio
import signal
import time
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from laptop_agents.core.logger import logger
from laptop_agents.core.orchestrator import append_event, PAPER_DIR
from laptop_agents.data.providers.bitunix_ws import BitunixWSProvider
from laptop_agents.paper.broker import PaperBroker
from laptop_agents.trading.helpers import Candle, Tick, normalize_candle_order
from laptop_agents.data.loader import load_bitunix_candles
from laptop_agents.resilience.trading_circuit_breaker import TradingCircuitBreaker
from laptop_agents.core.orchestrator import render_html, write_trades_csv, LATEST_DIR
from laptop_agents.core.hard_limits import MAX_ERRORS_PER_SESSION
import threading
import os
from laptop_agents.core.state_manager import StateManager
from laptop_agents.core.logger import write_alert
import psutil

@dataclass
class AsyncSessionResult:
    """Result of an async trading session."""
    iterations: int = 0
    trades: int = 0
    errors: int = 0
    starting_equity: float = 10000.0
    ending_equity: float = 10000.0
    duration_sec: float = 0.0
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
        provider: Optional[Any] = None,
        state_dir: Optional[Path] = None,
    ):
        from laptop_agents.core.orchestrator import PAPER_DIR
        self.state_dir = state_dir or PAPER_DIR
        self.symbol = symbol
        self.interval = interval
        self.strategy_config = strategy_config
        self.starting_equity = starting_balance
        self.status = "initializing"
        self.iterations = 0
        self.errors = 0
        self.consecutive_ws_errors: int = 0
        self.max_ws_errors: int = 3
        
        # New: Store risk parameters
        self.risk_pct = risk_pct
        self.stop_bps = stop_bps
        self.tp_r = tp_r
        
        # State
        self.latest_tick: Optional[Tick] = None
        self.candles: List[Candle] = []
        self.trades = 0
        
        # Components
        from laptop_agents.data.providers.bitunix_ws import BitunixWSProvider
        self.provider = provider or BitunixWSProvider(symbol)
        state_path = str(self.state_dir / "async_broker_state.json")
        from laptop_agents.paper.broker import PaperBroker
        self.broker = PaperBroker(
            symbol=symbol, 
            fees_bps=fees_bps, 
            slip_bps=slip_bps, 
            starting_equity=starting_balance,
            state_path=state_path
        )
        
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
                self.supervisor = Supervisor(provider=None, cfg=self.strategy_config, broker=self.broker)
                self.agent_state = AgentState(instrument=self.symbol, timeframe=self.interval)
            except Exception as e:
                logger.error(f"CONFIG_VALIDATION_FAILED: {e}")
                # Hard fail on startup as per Perfection Plan Phase 2.3
                raise ValueError(f"Invalid strategy configuration: {e}")
        
        # Control
        self.shutdown_event = asyncio.Event()
        self.start_time = time.time()
        from laptop_agents.core.orchestrator import REPO_ROOT
        self.kill_file = REPO_ROOT / "kill.txt"
        self.last_data_time: float = time.time()
        self.dry_run = dry_run
        self.stale_data_timeout_sec: float = float(stale_timeout)
        self.execution_latency_ms = execution_latency_ms
        
        self.circuit_breaker = TradingCircuitBreaker(max_daily_drawdown_pct=5.0, max_consecutive_losses=5)
        self.circuit_breaker.set_starting_equity(starting_balance)
        self.duration_min: int = 0  # Will be set in run()
        
        from laptop_agents.core.state_manager import StateManager
        self.state_manager = StateManager(self.state_dir)
        self.last_heartbeat_time: float = time.time()
        self.metrics: List[Dict[str, Any]] = []

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
                 logger.warning(f"Circuit breaker was previously TRIPPED ({self.circuit_breaker._trip_reason}). It remains TRIPPED.")
                 # Note: TradingCircuitBreaker doesn't have a direct 'trip()' method but is_tripped() checks state
        
        # Start Threaded Watchdog (independent of event loop)
        watchdog_thread = threading.Thread(target=self._threaded_watchdog, daemon=True)
        watchdog_thread.start()
        logger.info("Threaded watchdog started.")
        # Pre-load some historical candles if possible to seed strategy
        try:
            logger.info("Seeding historical candles via REST...")
            min_history = 100
            if self.strategy_config:
                min_history = self.strategy_config.get("engine", {}).get("min_history_bars", 100)
            
            self.candles = load_bitunix_candles(self.symbol, self.interval, limit=max(100, min_history))
            self.candles = normalize_candle_order(self.candles)
            logger.info(f"Seed complete: {len(self.candles)} candles")
            
            from laptop_agents.trading.helpers import detect_candle_gaps
            gaps = detect_candle_gaps(self.candles, self.interval)
            for gap in gaps:
                logger.warning(f"GAP_DETECTED: {gap['missing_count']} missing between {gap['prev_ts']} and {gap['curr_ts']}")
        except Exception as e:
            logger.warning(f"Failed to seed candles: {e}")

        # Start tasks
        tasks = [
            asyncio.create_task(self.market_data_task()),
            asyncio.create_task(self.watchdog_task()),
            asyncio.create_task(self.heartbeat_task()),
            asyncio.create_task(self.timer_task(end_time)),
            asyncio.create_task(self.kill_switch_task()),
            asyncio.create_task(self.stale_data_task()),
            asyncio.create_task(self.funding_task()),
        ]
        
        try:
            await self.shutdown_event.wait()
        finally:
            self.status = "shutting_down"
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Final cleanup
            if self.broker.pos and self.latest_tick:
                self.broker.close_all(self.latest_tick.last)
            
            try:
                await asyncio.wait_for(asyncio.to_thread(self.broker.shutdown), timeout=5.0)
            except asyncio.TimeoutError:
                logger.error("Broker shutdown timed out after 5s")
            
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
            
            # Generate final_report.json
            try:
                report_path = LATEST_DIR / "final_report.json"
                exit_code = 0 if self.errors == 0 else 1
                report = {
                    "status": "success" if exit_code == 0 else "error",
                    "exit_code": exit_code,
                    "pnl_absolute": round(self.broker.current_equity - self.starting_equity, 2),
                    "error_count": self.errors,
                    "duration_seconds": round(time.time() - self.start_time, 1),
                    "symbol": self.symbol,
                    "trades": self.trades
                }
                with open(report_path, "w") as f:
                    json.dump(report, f, indent=2)
                logger.info(f"Final report written to {report_path}")

                # 3.3 Post-Run Performance Summary (CLI)
                trades_list = [h for h in self.broker.order_history if h.get("type") == "exit"]
                wins = [t for t in trades_list if t.get("pnl", 0) > 0]
                win_rate = (len(wins) / len(trades_list) * 100) if trades_list else 0.0
                total_fees = sum(t.get("fees", 0) for t in trades_list)
                net_pnl = float(self.broker.current_equity - self.starting_equity)
                pnl_pct = (net_pnl / self.starting_equity * 100) if self.starting_equity > 0 else 0.0

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
                logger.error(f"Failed to write final report/summary: {re}")

            if self.errors > 0:
                write_alert(f"Session failed with {self.errors} errors")

    async def market_data_task(self):
        """Consumes WebSocket data and triggers strategy on candle closure."""
        try:
            async for item in self.provider.listen():
                if self.shutdown_event.is_set():
                    break
                    
                if isinstance(item, Tick):
                    self.latest_tick = item
                    self.last_data_time = time.time()
                    # Immediate watchdog check on EVERY tick is handled by watchdog_task
                    # but we could also trigger it here for even lower latency
                    
                elif isinstance(item, Candle):
                    # 1.1 Implement Gap Backfill Logic
                    try:
                        new_ts = int(item.ts)
                        interval_sec = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600}.get(self.interval, 60)
                        if self.candles:
                            last_ts = int(self.candles[-1].ts)
                            # If gap is more than 1.5x interval, we likely missed a candle
                            if (new_ts - last_ts) > interval_sec * 1.5:
                                logger.warning(f"GAP_DETECTED: {new_ts - last_ts}s missing between {last_ts} and {new_ts}. Attempting backfill...")
                                # Call provider method (public now)
                                await self.provider.fetch_and_inject_gap(last_ts, new_ts)
                    except (ValueError, TypeError, AttributeError) as ge:
                        logger.error(f"Error checking for gaps: {ge}")

                    # Check if this is a NEW candle or an update to the current one
                    if not self.candles or item.ts != self.candles[-1].ts:
                        # New candle! This means the previous one just closed.
                        if self.candles:
                            closed_candle = self.candles[-1]
                            await self.on_candle_closed(closed_candle)
                        
                        self.candles.append(item)
                        # Keep window size
                        if len(self.candles) > 200:
                            self.candles = self.candles[-200:]
                    else:
                        # Update current open candle
                        self.candles[-1] = item
                        
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in market_data_task: {e}")
            self.consecutive_ws_errors += 1
            self.errors += 1
            if self.consecutive_ws_errors >= self.max_ws_errors:
                logger.error(f"WS_FATAL: {self.max_ws_errors} consecutive errors. Triggering shutdown.")
                self.shutdown_event.set()

    async def kill_switch_task(self):
        """Monitors for kill.txt file to trigger emergency shutdown."""
        try:
            while not self.shutdown_event.is_set():
                if self.kill_file.exists():
                    logger.warning("KILL SWITCH ACTIVATED: kill.txt detected")
                    self.shutdown_event.set()
                    try:
                        self.kill_file.unlink()  # Remove file after processing
                    except Exception:
                        pass
                    break
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    async def stale_data_task(self):
        """Detects stale market data and triggers shutdown."""
        try:
            while not self.shutdown_event.is_set():
                age = time.time() - self.last_data_time
                if age > self.stale_data_timeout_sec:
                    logger.error(f"STALE DATA: No market data for {age:.0f}s. Shutting down.")
                    self.shutdown_event.set()
                    break
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass

    async def watchdog_task(self):
        """Checks open positions against latest tick every 100ms."""
        try:
            while not self.shutdown_event.is_set():
                if self.latest_tick and self.broker.pos:
                    events = self.broker.on_tick(self.latest_tick)
                    for exit_event in events.get("exits", []):
                        self.trades += 1
                        logger.info(f"WATCHDOG TRIGGERED EXIT: {exit_event['reason']} @ {exit_event['price']}")
                        append_event({
                            "event": "WatchdogExit",
                            "tick": vars(self.latest_tick),
                            **exit_event
                        }, paper=True)
                
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass

    async def on_candle_closed(self, candle: Candle):
        """Runs strategy logic when a candle is confirmed closed."""
        self.iterations += 1
        logger.info(f"Candle closed: {candle.ts} at {candle.close}")
        
        if hasattr(candle, 'volume') and float(candle.volume) == 0:
            logger.warning(f"LOW_VOLUME_WARNING: Candle {candle.ts} has zero volume")
        
        if self.circuit_breaker.is_tripped():
            logger.warning("SIGNAL BLOCKED: Circuit breaker is tripped.")
            return

        try:
            # Generate signal
            order = None
            raw_signal = None
            
            if self.strategy_config:
                try:
                    # Use persistent supervisor and state for high performance
                    self.agent_state.candles = self.candles[:-1]
                    self.agent_state = self.supervisor.step(self.agent_state, candle, skip_broker=True)
                    
                    if self.agent_state.setup.get("side") in ["LONG", "SHORT"]:
                        raw_signal = "BUY" if self.agent_state.setup["side"] == "LONG" else "SELL"
                except Exception as agent_err:
                    logger.error(f"AGENT_ERROR: Strategy agent failed, skipping signal: {agent_err}")
                    append_event({"event": "AgentError", "error": str(agent_err)}, paper=True)
                    raw_signal = None  # Suppress trade on agent failure
            
            if raw_signal:
                import random
                latency = random.randint(50, 500)
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
                        "sl": float(candle.close) - stop_distance if signal_side == "LONG" else float(candle.close) + stop_distance,
                        "tp": float(candle.close) + (stop_distance * self.tp_r) if signal_side == "LONG" else float(candle.close) - (stop_distance * self.tp_r),
                        "equity": self.broker.current_equity,
                        "client_order_id": f"async_{int(time.time())}_{self.iterations}"
                    }

            # Execute via broker
            current_tick = self.latest_tick
            if order and order.get("go"):
                if not self.dry_run:
                    import random
                    latency = random.randint(50, 500)
                    logger.info(f"Simulating latency: {latency}ms")
                    await asyncio.sleep(latency / 1000.0)
                    # After sleep, we MUST use the newest tick for fill price to avoid look-ahead bias
                    current_tick = self.latest_tick

            events = self.broker.on_candle(candle, order, tick=current_tick)
            
            for fill in events.get("fills", []):
                self.trades += 1
                logger.info(f"STRATEGY FILL: {fill['side']} @ {fill['price']}")
                append_event({"event": "StrategyFill", **fill}, paper=True)
                
            for exit_event in events.get("exits", []):
                self.trades += 1
                logger.info(f"STRATEGY EXIT: {exit_event['reason']} @ {exit_event['price']}")
                append_event({"event": "StrategyExit", **exit_event}, paper=True)

            # Update circuit breaker
            trade_pnl = None
            for exit_event in events.get("exits", []):
                trade_pnl = exit_event.get("pnl", 0)
                
            self.circuit_breaker.update_equity(self.broker.current_equity, trade_pnl)

            if self.circuit_breaker.is_tripped():
                logger.warning(f"CIRCUIT BREAKER TRIPPED: {self.circuit_breaker.get_status()}")
                self.shutdown_event.set()

            # Save state (skip in dry_run for performance/stress-tests)
            if not self.dry_run:
                self.state_manager.set_circuit_breaker_state(self.circuit_breaker.get_status())
                self.state_manager.save()

        except Exception as e:
            logger.error(f"Error in on_candle_closed: {e}")
            self.errors += 1
            if self.errors >= MAX_ERRORS_PER_SESSION:
                logger.error(f"ERROR BUDGET EXHAUSTED: {self.errors} errors. Shutting down.")
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
                price = self.latest_tick.last if self.latest_tick else (self.candles[-1].close if self.candles else 0.0)
                
                unrealized = self.broker.get_unrealized_pnl(price)
                total_equity = self.broker.current_equity + unrealized
                
                process = psutil.Process()
                mem_mb = process.memory_info().rss / 1024 / 1024
                cpu_pct = process.cpu_percent()

                if mem_mb > 1024:
                    logger.critical(f"High Memory Usage: {mem_mb:.1f} MB. Triggering shutdown.")
                    self.shutdown_event.set()

                # Write heartbeat file for watchdog
                with heartbeat_path.open("w") as f:
                    json.dump({
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "unix_ts": time_module.time(),
                        "last_updated_ts": time_module.time(),
                        "elapsed": elapsed,
                        "equity": total_equity,
                        "symbol": self.symbol,
                        "ram_mb": round(mem_mb, 2),
                        "cpu_pct": cpu_pct
                    }, f)
                
                remaining = max(0, (self.start_time + (self.duration_min * 60)) - time.time())
                remaining_str = f"{int(remaining // 60)}:{int(remaining % 60):02d}"

                logger.info(
                    f"[ASYNC] {self.symbol} | Price: {price:,.2f} | Pos: {pos_str:5} | "
                    f"Equity: ${total_equity:,.2f} | "
                    f"Elapsed: {elapsed:.0f}s | Remaining: {remaining_str}"
                )
                
                append_event({
                    "event": "AsyncHeartbeat",
                    "price": price,
                    "pos": pos_str,
                    "equity": total_equity,
                    "unrealized": unrealized,
                    "elapsed": elapsed
                }, paper=True)
                
                # Collect metric data point
                self.metrics.append({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "elapsed": elapsed,
                    "equity": total_equity,
                    "price": price,
                    "unrealized": unrealized,
                    "errors": self.errors
                })
                
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
                if now.hour in [0, 8, 16] and now.minute == 0 and now.hour != last_funding_hour:
                    logger.info(f"Funding window detected at {now.hour:02d}:00 UTC")
                    rate = await self.provider.funding_rate()
                    logger.info(f"FUNDING APPLIED: Rate {rate:.6f}")
                    self.broker.apply_funding(rate, now.isoformat())
                    last_funding_hour = now.hour
                
                if now.minute != 0:
                    last_funding_hour = None
                    
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            pass

    def _threaded_watchdog(self):
        """Independent thread that kills the process if main loop freezes."""
        while not self.shutdown_event.is_set():
            age = time.time() - self.last_heartbeat_time
            if age > 30:
                # Use critical print as logger might be stuck too
                print(f"\n\n!!! WATCHDOG FATAL: Main loop frozen for {age:.1f}s. FORCE EXITing. !!!\n\n")
                logger.critical(f"WATCHDOG_FATAL: Main loop frozen for {age:.1f}s. HARD EXIT.")
                os._exit(1)
            time.sleep(1)

async def run_async_session(
    duration_min: int = 10,
    symbol: str = "BTCUSDT",
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
) -> AsyncSessionResult:
    """Entry point for the async session."""
    
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
        provider=None
    )
    
    if replay_path:
        from laptop_agents.backtest.replay_runner import ReplayProvider
        runner.provider = ReplayProvider(Path(replay_path))
        logger.info(f"Using REPLAY PROVIDER from {replay_path}")
    
    # Handle OS signals (skip on Windows if not supported)
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, runner.shutdown_event.set)
    except (NotImplementedError, AttributeError):
        # Fallback for Windows or environments where signal handlers are not available
        logger.warning("Signal handlers not supported in this environment (likely Windows). Use Ctrl+C or wait for duration limit.")
        # On Windows, KeyboardInterrupt is caught by the asyncio.run block in main() or here.
        # We can add a small hack to check for it, but usually asyncio.run handles it.
        
    try:
        await runner.run(duration_min)
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Initiating graceful shutdown...")
        runner.shutdown_event.set()
        # Give it a moment to clean up
        await asyncio.sleep(1.0)
    except Exception as e:
        logger.error(f"Fatal error in async session: {e}")
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
            "last_close": float(runner.candles[-1].close) if runner.candles else 0.0,
            "fees_bps": fees_bps,
            "slip_bps": slip_bps,
            "starting_balance": starting_balance,
            "ending_balance": runner.broker.current_equity,
            "net_pnl": runner.broker.current_equity - starting_balance,
            "trades": runner.trades,
            "mode": "async",
        }
        render_html(summary, [], "", candles=runner.candles)
        logger.info(f"HTML report generated at {LATEST_DIR / 'summary.html'}")
    except Exception as e:
        logger.error(f"Failed to generate HTML report: {e}")

    return AsyncSessionResult(
        iterations=runner.iterations,
        trades=runner.trades,
        errors=runner.errors,
        starting_equity=runner.starting_equity,
        ending_equity=runner.broker.current_equity,
        duration_sec=time.time() - runner.start_time
    )
