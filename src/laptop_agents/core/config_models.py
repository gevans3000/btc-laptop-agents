from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional


class EngineConfig(BaseModel):
    pending_trigger_max_bars: int = 24
    derivatives_refresh_bars: int = 6
    min_history_bars: int = 100


class RiskConfig(BaseModel):
    equity: Optional[float] = 10000.0
    risk_pct: float = 1.0
    rr_min: float = 1.5


class StrategyConfig(BaseModel):
    """
    Validation schema for the trading strategy configuration.
    Ensures that all required sub-sections and keys are present.
    """

    engine: EngineConfig = Field(default_factory=lambda: EngineConfig())
    derivatives_gates: Dict[str, Any] = Field(default_factory=lambda: {})
    setups: Dict[str, Any] = Field(default_factory=lambda: {})
    risk: RiskConfig = Field(default_factory=lambda: RiskConfig())
    cvd: Dict[str, Any] = Field(default_factory=lambda: {})

    @classmethod
    def validate_config(cls, config: Dict[str, Any]) -> StrategyConfig:
        """Helper to validate a dict against the model."""
        return cls(**config)
