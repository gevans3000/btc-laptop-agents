from pathlib import Path

# Repository paths
HERE = Path(__file__).parent.resolve()
REPO_ROOT = HERE.parent.parent

# Default settings
DEFAULT_SYMBOL = "BTCUSDT"

# Hard-coded safety limits
MAX_POSITION_SIZE_USD = 500.0
MAX_POSITION_ABS = 1.0
MAX_DAILY_LOSS_USD = 50.0
MAX_DAILY_LOSS_PCT = 5.0
MAX_ORDERS_PER_MINUTE = 10
MIN_RR_RATIO = 1.0
MAX_LEVERAGE = 1.0
MAX_ERRORS_PER_SESSION = 20
MAX_SINGLE_TRADE_LOSS_USD = 100.0
MAX_CANDLE_BUFFER = 500
