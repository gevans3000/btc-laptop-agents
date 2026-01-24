from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from laptop_agents.constants import DEFAULT_SYMBOL, WORKSPACE_PAPER_DIR
from laptop_agents.core.config_models import StrategyConfig
from laptop_agents.core.logger import logger


@dataclass
class SessionConfig:
    symbol: str = DEFAULT_SYMBOL
    interval: str = "1m"
    strategy_config: Optional[Dict[str, Any]] = None
    starting_balance: float = 10000.0
    risk_pct: float = 1.0
    stop_bps: float = 30.0
    tp_r: float = 1.5
    fees_bps: float = 2.0
    slip_bps: float = 0.5
    stale_timeout: int = 120
    execution_latency_ms: int = 200
    dry_run: bool = False
    provider: Any = None
    execution_mode: str = "paper"
    state_dir: Path = field(default_factory=lambda: WORKSPACE_PAPER_DIR)

    # Internal session state
    loop_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    start_time: float = field(default_factory=time.time)

    def validate(self) -> None:
        """Validate strategy configuration if present."""
        if self.strategy_config:
            try:
                validated = StrategyConfig.validate_config(self.strategy_config)
                self.strategy_config = validated.model_dump()
                logger.info("Strategy configuration validated successfully.")
            except Exception as e:
                logger.error(f"CONFIG_VALIDATION_FAILED: {e}")
                raise ValueError(f"Invalid strategy configuration: {e}")

    @classmethod
    def from_params(cls, **kwargs) -> SessionConfig:
        """Create a SessionConfig object from raw parameters."""
        # Ensure state_dir is a Path object
        if "state_dir" in kwargs and kwargs["state_dir"]:
            kwargs["state_dir"] = Path(kwargs["state_dir"])
        else:
            kwargs["state_dir"] = WORKSPACE_PAPER_DIR

        return cls(**kwargs)
