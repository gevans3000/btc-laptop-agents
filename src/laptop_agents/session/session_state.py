from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from laptop_agents.core.logger import logger

if TYPE_CHECKING:
    from laptop_agents.session.async_session import AsyncRunner


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


def restore_starting_balance(state_path: Path, starting_balance: float) -> float:
    if not state_path.exists():
        return starting_balance
    try:
        with state_path.open("r") as f:
            state = json.load(f)
        restored_equity = state.get("starting_equity")
        if restored_equity:
            logger.info(
                f"RECOVERY: Restored starting_equity from state: ${restored_equity:,.2f}"
            )
            return float(restored_equity)
    except Exception as e:
        logger.warning(f"Failed to restore starting_equity from state: {e}")
    return starting_balance


def build_session_result(runner: "AsyncRunner") -> AsyncSessionResult:
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
