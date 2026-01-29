import asyncio
import os
from laptop_agents.core.logger import logger, write_alert


async def equity_sentinel_task(runner):
    """
    Monitors account equity in real-time.
    Triggers global kill switch if equity drops below hard stop threshold.
    """
    starting_equity = runner.starting_equity
    # Hard stop at -20% of session starting balance
    hard_stop_threshold = starting_equity * 0.8

    logger.info(
        f"Equity Sentinel active. Hard stop at ${hard_stop_threshold:,.2f} (-20%)"
    )

    while not runner.shutdown_event.is_set():
        try:
            # Calculate total account equity (Balance + Unrealized)
            current_price = runner.latest_tick.last if runner.latest_tick else 0
            unrealized = 0
            if current_price > 0:
                unrealized = runner.broker.get_unrealized_pnl(current_price)

            total_equity = runner.broker.current_equity + unrealized

            if total_equity < hard_stop_threshold:
                logger.critical(
                    f"HARD STOP BREACHED! Equity ${total_equity:,.2f} < Threshold ${hard_stop_threshold:,.2f}"
                )
                write_alert(
                    f"FATAL: Hard stop breached. Current Equity: ${total_equity:,.2f}"
                )

                # Activate Kill Switch
                os.environ["LA_KILL_SWITCH"] = "TRUE"

                # Close all positions
                if hasattr(runner.broker, "close_all"):
                    runner.broker.close_all(current_price)

                # Shutdown session
                runner._request_shutdown("hard_stop_breached")
                break

            await asyncio.sleep(5)  # Check every 5 seconds
        except Exception as e:
            logger.error(f"Error in equity sentinel: {e}")
            await asyncio.sleep(10)
