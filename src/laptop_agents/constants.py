import os
import yaml
from pathlib import Path

# Repository paths
HERE = Path(__file__).parent.resolve()
src_dir = HERE.parent
if (src_dir / "laptop_agents").exists():
    # We are in src/laptop_agents
    REPO_ROOT = src_dir.parent
else:
    # Fallback
    REPO_ROOT = Path(os.getcwd())

WORKSPACE_DIR = REPO_ROOT / ".workspace"
WORKSPACE_RUNS_DIR = WORKSPACE_DIR / "runs"
WORKSPACE_PAPER_DIR = WORKSPACE_DIR / "paper"
WORKSPACE_LOGS_DIR = WORKSPACE_DIR / "logs"
WORKSPACE_LOCKS_DIR = WORKSPACE_DIR / "locks"
AGENT_PID_FILE = WORKSPACE_DIR / "agent.pid"

# Default settings
DEFAULT_SYMBOL = "BTCUSDT"

# Load defaults
CONFIG_DEFAULTS_PATH = REPO_ROOT / "config" / "defaults.yaml"


def _load_defaults():
    defaults = {}
    if CONFIG_DEFAULTS_PATH.exists():
        try:
            with open(CONFIG_DEFAULTS_PATH, "r") as f:
                defaults = yaml.safe_load(f) or {}
        except Exception:
            pass
    return defaults


_DEFAULTS = _load_defaults()
_TRADING = _DEFAULTS.get("trading", {})
_SYSTEM = _DEFAULTS.get("system", {})

# Hard-coded safety limits (Overridden by config if present, else fallback)
MAX_POSITION_SIZE_USD = float(_TRADING.get("max_position_size_usd", 200000.0))
MAX_POSITION_ABS = 1.0
MAX_DAILY_LOSS_USD = float(_TRADING.get("max_daily_loss_usd", 50.0))
MAX_DAILY_LOSS_PCT = 5.0
MAX_ORDERS_PER_MINUTE = 10
MIN_RR_RATIO = float(_TRADING.get("tp_r", 1.0))
MAX_LEVERAGE = float(_TRADING.get("max_leverage", 1.0))
MAX_ERRORS_PER_SESSION = 20
MAX_SINGLE_TRADE_LOSS_USD = 100.0
MAX_CANDLE_BUFFER = 500
