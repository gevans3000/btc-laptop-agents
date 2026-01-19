from typing import Dict, Optional
from pydantic import BaseModel, ConfigDict, Field, ValidationError
import yaml
from laptop_agents.constants import REPO_ROOT
from laptop_agents.core.logger import logger


class RiskConfig(BaseModel):
    max_position_per_symbol: Dict[str, float] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class ExchangeFees(BaseModel):
    maker: float
    taker: float


class ExchangeConfig(BaseModel):
    fees: Optional[ExchangeFees] = None

    model_config = ConfigDict(extra="allow")


def load_and_validate_risk_config() -> RiskConfig:
    path = REPO_ROOT / "config" / "risk.yaml"
    if not path.exists():
        logger.warning(f"Config file not found: {path} (using defaults)")
        return RiskConfig()

    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        return RiskConfig(**data)
    except ValidationError as e:
        logger.error(f"Risk config validation failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Failed to load risk config: {e}")
        raise


def validate_runtime_config(
    risk_pct: float, stop_bps: float, starting_balance: float
) -> None:
    """Validate runtime arguments passed to the orchestrator."""
    errors = []
    if risk_pct <= 0:
        errors.append(f"risk_pct must be > 0 (got {risk_pct})")
    if stop_bps <= 0:
        errors.append(f"stop_bps must be > 0 (got {stop_bps})")
    if starting_balance <= 0:
        errors.append(f"starting_balance must be > 0 (got {starting_balance})")

    if errors:
        raise ValueError("Config validation failed: " + "; ".join(errors))
