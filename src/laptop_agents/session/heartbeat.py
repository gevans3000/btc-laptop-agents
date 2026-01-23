from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import psutil

from laptop_agents import constants as hard_limits
from laptop_agents.constants import MAX_ERRORS_PER_SESSION
from laptop_agents.core.logger import logger
from laptop_agents.core.orchestrator import append_event

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


async def heartbeat_task(runner: "AsyncRunner") -> None:
    """Logs system status every second."""
    import time as time_module

    heartbeat_path = Path("logs/heartbeat.json")
    heartbeat_path.parent.mkdir(exist_ok=True)

    try:
        while not runner.shutdown_event.is_set():
            try:
                elapsed = time.time() - runner.start_time
                pos_str = runner.broker.pos.side if runner.broker.pos else "FLAT"
                open_orders_count = len(getattr(runner.broker, "working_orders", []))
                price = (
                    runner.latest_tick.last
                    if runner.latest_tick
                    else (runner.candles[-1].close if runner.candles else 0.0)
                )

                unrealized = runner.broker.get_unrealized_pnl(price)
                total_equity = runner.broker.current_equity + unrealized

                # Update max drawdown tracking
                runner.max_equity = max(runner.max_equity, total_equity)
                dd = (
                    (runner.max_equity - total_equity) / runner.max_equity
                    if runner.max_equity > 0
                    else 0
                )
                runner.max_drawdown = max(runner.max_drawdown, dd)

                max_loss_usd = hard_limits.MAX_DAILY_LOSS_USD
                drawdown_usd = runner.starting_equity - total_equity
                if (
                    runner.starting_equity > 0
                    and drawdown_usd >= max_loss_usd
                    and not runner.kill_switch_triggered
                ):
                    logger.critical(
                        "RISK KILL SWITCH TRIPPED",
                        {
                            "event": "RiskKillSwitch",
                            "symbol": runner.symbol,
                            "loop_id": runner.loop_id,
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
                            "symbol": runner.symbol,
                            "loop_id": runner.loop_id,
                            "position": pos_str,
                            "open_orders_count": open_orders_count,
                            "equity": total_equity,
                            "drawdown_usd": drawdown_usd,
                            "limit_usd": max_loss_usd,
                        },
                        paper=True,
                    )
                    runner.kill_switch_triggered = True
                    runner._request_shutdown("max_loss_usd")
                    try:
                        runner.broker.cancel_all_open_orders()
                        if price and price > 0:
                            runner.broker.close_all(price)
                    except Exception as e:
                        logger.exception(
                            "Risk kill switch cleanup failed",
                            {
                                "event": "RiskKillSwitchCleanupError",
                                "symbol": runner.symbol,
                                "loop_id": runner.loop_id,
                                "position": pos_str,
                                "open_orders_count": open_orders_count,
                                "interval": runner.interval,
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
                    runner._request_shutdown("memory_limit")

                # Save last price cache
                if runner.latest_tick:
                    try:
                        price_cache_path = Path("paper/last_price_cache.json")
                        price_cache_path.parent.mkdir(exist_ok=True)
                        with open(price_cache_path, "w") as f:
                            json.dump(
                                {
                                    "last": runner.latest_tick.last,
                                    "ts": runner.latest_tick.ts,
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
                            "symbol": runner.symbol,
                            "ram_mb": round(mem_mb, 2),
                            "cpu_pct": cpu_pct,
                        },
                        f,
                    )

                remaining = max(
                    0, (runner.start_time + (runner.duration_min * 60)) - time.time()
                )
                remaining_str = f"{int(remaining // 60)}:{int(remaining % 60):02d}"

                logger.info(
                    f"[ASYNC] {runner.symbol} | Price: {price:,.2f} | Pos: {pos_str:5} | "
                    f"Equity: ${total_equity:,.2f} | "
                    f"Elapsed: {elapsed:.0f}s | Remaining: {remaining_str}",
                    {
                        "event": "Heartbeat",
                        "symbol": runner.symbol,
                        "loop_id": runner.loop_id,
                        "position": pos_str,
                        "open_orders_count": open_orders_count,
                    },
                )

                append_event(
                    {
                        "event": "AsyncHeartbeat",
                        "symbol": runner.symbol,
                        "loop_id": runner.loop_id,
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
                runner.metrics.append(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "elapsed": elapsed,
                        "equity": total_equity,
                        "price": price,
                        "unrealized": unrealized,
                        "errors": runner.errors,
                    }
                )

                runner.last_heartbeat_time = time.time()
            except Exception as e:
                logger.exception(f"Heartbeat task error: {e}")
                runner.errors += 1
                pos_str = runner.broker.pos.side if runner.broker.pos else "FLAT"
                open_orders_count = len(getattr(runner.broker, "working_orders", []))
                append_event(
                    {
                        "event": "HeartbeatTaskError",
                        "error": str(e),
                        "symbol": runner.symbol,
                        "loop_id": runner.loop_id,
                        "position": pos_str,
                        "open_orders_count": open_orders_count,
                        "interval": runner.interval,
                    },
                    paper=True,
                )
                if (
                    runner.errors >= MAX_ERRORS_PER_SESSION
                    and not runner.shutdown_event.is_set()
                ):
                    runner._request_shutdown("error_budget")
            await asyncio.sleep(10.0)
    except asyncio.CancelledError:
        pass
