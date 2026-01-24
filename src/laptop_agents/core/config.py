from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator
import json


class RiskConfig(BaseModel):
    risk_pct: float = Field(default=1.0, ge=0.1, le=10.0)
    stop_bps: float = Field(default=30.0, ge=5.0)
    tp_r: float = Field(default=1.5, ge=0.5)
    max_leverage: float = Field(default=1.0, ge=1.0, le=20.0)


class StrategyConfig(BaseModel):
    name: str = "default"
    params: Dict[str, Any] = Field(default_factory=dict)
    risk: RiskConfig = Field(default_factory=RiskConfig)


class SessionConfig(BaseModel):
    symbol: str = "BTCUSDT"
    interval: str = "1m"
    source: str = "mock"
    duration: int = 10
    execution_mode: str = "paper"
    fees_bps: float = 2.0
    slip_bps: float = 0.5
    dry_run: bool = False
    kill_switch: bool = False

    @property
    def artifact_dir(self) -> Path:
        """Derived directory for all run-time artifacts."""
        from laptop_agents.constants import REPO_ROOT

        return REPO_ROOT / ".workspace"

    @field_validator("symbol", mode="before")
    def normalize_symbol(cls, v: str) -> str:
        """
        Normalize trading symbol (e.g. BTC/USDT -> BTCUSDT).
        Default is BTCUSDT if not specified via Env (LA_SYMBOL) or Args.
        """
        if not v:
            # Pydantic default will handle this if v is None, but if empty string:
            return "BTCUSDT"
        return v.upper().replace("/", "").replace("-", "")


def load_session_config(
    config_path: Optional[Path] = None,
    strategy_name: Optional[str] = None,
    overrides: Optional[Dict[str, Any]] = None,
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
    for key in SessionConfig.model_fields.keys():
        env_val = os.environ.get(f"LA_{key.upper()}")
        if env_val:
            data[key] = env_val

    # 4. Overrides (CLI flags)
    if overrides:
        data.update({k: v for k, v in overrides.items() if v is not None})

    # 5. Environment Kill Switch (Override everything for safety)
    if os.environ.get("LA_KILL_SWITCH", "FALSE").upper() == "TRUE":
        data["kill_switch"] = True

    config = SessionConfig(**data)

    # 5. Fail Fast Validation
    if config.execution_mode == "live":
        api_key = os.environ.get("BITUNIX_API_KEY")
        api_secret = os.environ.get("BITUNIX_API_SECRET")
        if not api_key or not api_secret:
            raise ValueError(
                "STRICT CONFIGURATION ERROR: Live mode requires "
                "BITUNIX_API_KEY and BITUNIX_API_SECRET environment variables. "
                "Please run 'la doctor --fix' to initialize .env and add your credentials."
            )

    return config


class RunResult(BaseModel):
    success: bool
    exit_code: int = 0
    errors: List[str] = Field(default_factory=list)
    artifacts: Dict[str, str] = Field(default_factory=dict)
    summary: Dict[str, Any] = Field(default_factory=dict)


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge dicts (override wins)."""
    out: Dict[str, Any] = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_strategy_config(
    strategy_name: str,
    *,
    overrides: Optional[Dict[str, Any]] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Load a strategy config dict with precedence:
      overrides > config/strategies/<name>.json > built-in defaults

    Note: session config precedence (SessionConfig) is handled separately.
    """
    root = repo_root or Path(__file__).resolve().parent.parent.parent.parent
    strat_path = root / "config" / "strategies" / f"{strategy_name}.json"

    # Built-in defaults (minimal schema that passes StrategyConfig validation).
    data: Dict[str, Any] = {
        "engine": {},
        "derivatives_gates": {},
        "setups": {"default": {"active": True, "params": {}}},
        "risk": {"equity": 10000.0, "risk_pct": 1.0, "rr_min": 1.5},
        "cvd": {},
    }

    if strat_path.exists():
        with open(strat_path) as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            data = _deep_merge(data, loaded)

    if overrides:
        data = _deep_merge(data, {k: v for k, v in overrides.items() if v is not None})

    return data
