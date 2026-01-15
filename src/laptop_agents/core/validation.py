import os
from typing import Any, Dict
from laptop_agents.core.logger import logger
from laptop_agents.core import hard_limits

def validate_config(args: Any, strategy_config: Dict[str, Any]) -> None:
    """
    Validate CLI arguments and strategy configuration.
    Raises ValueError if validation fails.
    """
    # 1. Environment Variables Check for Live Modes
    if args.mode in ["live", "live-session"]:
        keys = ["BITUNIX_API_KEY", "BITUNIX_API_SECRET"]
        missing = [k for k in keys if not os.environ.get(k)]
        if missing:
            raise ValueError(f"Missing required environment variables for live mode: {', '.join(missing)}")

    # 2. Risk Parameter Validation
    risk_pct = args.risk_pct
    stop_bps = args.stop_bps
    max_leverage = args.max_leverage

    if not (0.1 <= risk_pct <= 5.0):
        raise ValueError(f"risk_pct must be between 0.1 and 5.0, got {risk_pct}")
    
    if stop_bps <= 5:
        raise ValueError(f"stop_bps must be greater than 5, got {stop_bps}")
    
    if max_leverage > hard_limits.MAX_LEVERAGE:
        raise ValueError(f"max_leverage {max_leverage} exceeds hard limit {hard_limits.MAX_LEVERAGE}")

    # 3. Strategy Config Validation (basic structure)
    if strategy_config:
        # Example check if 'risk' section exists
        if "risk" in strategy_config:
            s_risk = strategy_config["risk"]
            if "risk_pct" in s_risk:
                val = s_risk["risk_pct"]
                if not (0.1 <= val <= 5.0):
                     raise ValueError(f"Strategy risk_pct {val} must be between 0.1 and 5.0")

    logger.info("Configuration validation passed.")

def validate_events_jsonl(events_path: Any, append_event_fn: Any = None) -> tuple[bool, str]:
    """Validate that events.jsonl exists and is valid JSONL."""
    import json
    from pathlib import Path
    p = Path(events_path)
    if not p.exists():
        return False, f"File {p} not found"
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    json.loads(line)
        return True, "Valid"
    except Exception as e:
        return False, str(e)

def validate_trades_csv(trades_path: Any) -> tuple[bool, str]:
    """Validate that trades.csv exists."""
    from pathlib import Path
    p = Path(trades_path)
    if not p.exists():
        return False, f"File {p} not found"
    return True, "Valid"

def validate_summary_html(summary_path: Any) -> tuple[bool, str]:
    """Validate that summary.html exists."""
    from pathlib import Path
    p = Path(summary_path)
    if not p.exists():
        return False, f"File {p} not found"
    return True, "Valid"
