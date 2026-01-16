from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, validator
import json

class RiskConfig(BaseModel):
    risk_pct: float = Field(default=1.0, ge=0.1, le=10.0)
    stop_bps: float = Field(default=30.0, ge=5.0)
    tp_r: float = Field(default=1.5, ge=0.5)
    max_leverage: float = Field(default=1.0, ge=1.0, le=20.0)

class StrategyConfig(BaseModel):
    name: str = "default"
    params: Dict[str, Any] = {}
    risk: RiskConfig = Field(default_factory=RiskConfig)

class SessionConfig(BaseModel):
    symbol: str = "BTCUSD"
    interval: str = "1m"
    source: str = "mock"
    duration: int = 10
    execution_mode: str = "paper"
    fees_bps: float = 2.0
    slip_bps: float = 0.5
    async_mode: bool = True
    dry_run: bool = False
    
    @validator("symbol")
    def normalize_symbol(cls, v):
        return v.upper().replace("/", "").replace("-", "")

def load_session_config(
    config_path: Optional[Path] = None,
    strategy_name: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None
) -> SessionConfig:
    """Load and validate session configuration with priority: overrides > config_file > strategy > defaults."""
    data = {}
    
    # 1. Base defaults or Strategy defaults
    if strategy_name:
        # Try to load from config/strategies/
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        strat_path = repo_root / "config" / "strategies" / f"{strategy_name}.json"
        if strat_path.exists():
            with open(strat_path) as f:
                data.update(json.load(f))
                
    # 2. Config File
    if config_path and config_path.exists():
        with open(config_path) as f:
            data.update(json.load(f))
            
    # 3. Environment Variables (LA_ prefix)
    for key in SessionConfig.__fields__.keys():
        env_val = os.environ.get(f"LA_{key.upper()}")
        if env_val:
            data[key] = env_val
            
    # 4. Overrides (CLI flags)
    if overrides:
        data.update({k: v for k, v in overrides.items() if v is not None})
        
    return SessionConfig(**data)

class RunResult(BaseModel):
    success: bool
    exit_code: int = 0
    errors: List[str] = []
    artifacts: Dict[str, str] = {}
    summary: Dict[str, Any] = {}
