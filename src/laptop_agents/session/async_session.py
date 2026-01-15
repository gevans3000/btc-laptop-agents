from __future__ import annotations

import asyncio
import signal
import time
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
from laptop_agents.core import hard_limits

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
    ):
        self.symbol = symbol
        self.interval = interval
        self.strategy_config = strategy_config
        self.starting_equity = starting_balance
        self.status = "initializing"
        self.iterations = 0
        self.errors = 0
        
        # New: Store risk parameters
        self.risk_pct = risk_pct
        self.stop_bps = stop_bps
        self.tp_r = tp_r
        
        # State
        self.latest_tick: Optional[Tick] = None
        self.candles: List[Candle] = []
        self.trades = 0
        
        # Components
        self.provider = BitunixWSProvider(symbol)
        state_path = str(PAPER_DIR / "async_broker_state.json")
        self.broker = PaperBroker(
            symbol=symbol, 
            fees_bps=fees_bps, 
            slip_bps=slip_bps, 
            starting_equity=starting_balance,
            state_path=state_path
        )
        
        # Control
        self.shutdown_event = asyncio.Event()
        self.start_time = time.time()
        self.kill_file = Path("kill.txt")
        self.last_data_time: float = time.time()
        self.stale_data_timeout_sec: float = float(stale_timeout)
        
        self.circuit_breaker = TradingCircuitBreaker(max_daily_drawdown_pct=5.0, max_consecutive_losses=5)
        self.circuit_breaker.set_starting_equity(starting_balance)
        self.duration_min: int = 0  # Will be set in run()

    async def run(self, duration_min: int):
        """Main entry point to run the async loop."""
        self.duration_min = duration_min
        end_time = self.start_time + (duration_min * 60)
        self.status = "running"
        
        # Pre-load some historical candles if possible to seed strategy
        try:
            logger.info("Seeding historical candles via REST...")
            self.candles = load_bitunix_candles(self.symbol, self.interval, limit=100)
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
            self.errors += 1

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
        
        try:
            # Generate signal
            order = None
            raw_signal = None
            
            if self.strategy_config:
                from laptop_agents.agents.supervisor import Supervisor
                from laptop_agents.agents.state import State as AgentState
                
                # We use historical candles minus the one just closed for state, 
                # then step with the closed one.
                supervisor = Supervisor(provider=None, cfg=self.strategy_config, broker=self.broker)
                state = AgentState(instrument=self.symbol, timeframe=self.interval, candles=self.candles[:-1])
                state = supervisor.step(state, candle, skip_broker=True)
                
                if state.setup.get("side") in ["LONG", "SHORT"]:
                    raw_signal = "BUY" if state.setup["side"] == "LONG" else "SELL"
            
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
                        "sl": float(candle.close) - stop_distance if signal_side == "LONG" else float(candle.close) + stop_distance,
                        "tp": float(candle.close) + (stop_distance * self.tp_r) if signal_side == "LONG" else float(candle.close) - (stop_distance * self.tp_r),
                        "equity": self.broker.current_equity,
                        "client_order_id": f"async_{int(time.time())}_{self.iterations}"
                    }

            # Execute via broker
            events = self.broker.on_candle(candle, order)
            
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

        except Exception as e:
            logger.error(f"Error in on_candle_closed: {e}")
            self.errors += 1
            if self.errors >= hard_limits.MAX_ERRORS_PER_SESSION:
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
                
                # Write heartbeat file for watchdog
                with heartbeat_path.open("w") as f:
                    json.dump({
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "unix_ts": time_module.time(),
                        "elapsed": elapsed,
                        "equity": total_equity,
                        "symbol": self.symbol,
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
        stale_timeout=stale_timeout
    )
    
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
