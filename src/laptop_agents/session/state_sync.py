from __future__ import annotations

from typing import TYPE_CHECKING
from laptop_agents.core.logger import logger
from laptop_agents import constants as hard_limits

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


def sync_initial_state(runner: "AsyncRunner", starting_balance: float) -> float:
    """
    Synchronizes the broker's starting equity with the session's intended starting balance.
    Handles legacy state restoration and drawdown resets.
    Returns the resolved starting_equity.
    """
    # Restore starting equity from broker (if it was NOT restored from unified state already)
    # If starting_balance is NOT the default, it means it was likely restored from unified state
    is_restored = starting_balance != 10000.0

    final_starting_equity = starting_balance

    if not is_restored and runner.broker.starting_equity is not None:
        logger.info(
            f"Restoring starting equity from broker state: ${runner.broker.starting_equity:,.2f}"
        )
        final_starting_equity = runner.broker.starting_equity
    else:
        # Sync broker to our master starting_equity
        runner.broker.starting_equity = starting_balance

    # Ensure starting_equity is in state_manager for unified restoration
    runner.state_manager.set("starting_equity", final_starting_equity)
    runner.state_manager.save()

    # Reset stale drawdown state if no open exposure (avoid immediate kill switch)
    try:
        has_open_orders = bool(getattr(runner.broker, "working_orders", []))
        if (
            runner.broker.pos is None
            and not has_open_orders
            and final_starting_equity > 0
        ):
            drawdown_usd = final_starting_equity - float(runner.broker.current_equity)
            if drawdown_usd >= hard_limits.MAX_DAILY_LOSS_USD:
                logger.warning(
                    "STARTUP_DRAWDOWN_RESET: resetting starting equity after stale drawdown",
                    {
                        "event": "StartupDrawdownReset",
                        "symbol": runner.symbol,
                        "loop_id": runner.loop_id,
                        "position": "FLAT",
                        "open_orders_count": 0,
                        "starting_equity": final_starting_equity,
                        "current_equity": runner.broker.current_equity,
                        "drawdown_usd": drawdown_usd,
                    },
                )
                final_starting_equity = float(runner.broker.current_equity)
                runner.broker.starting_equity = final_starting_equity
                runner.state_manager.set("starting_equity", final_starting_equity)
                runner.state_manager.save()
    except Exception as e:
        logger.error(f"Failed to normalize startup equity: {e}")

    return final_starting_equity
