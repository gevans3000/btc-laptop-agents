"""
Hard-coded safety limits that cannot be overridden by user configuration.
Acting as a 'hardware' ceiling for the trading agents.
"""

MAX_POSITION_SIZE_USD = 200000.0  # Absolute max for any single trade
MAX_DAILY_LOSS_USD = 50.0       # Halt if we lose this much in today's runs
MAX_DAILY_LOSS_PCT = 5.0        # Max daily drawdown percentage
MAX_ORDERS_PER_MINUTE = 10      # Rate limit for orders
MIN_RR_RATIO = 1.0              # Reject trades with R:R below this
MAX_LEVERAGE = 20.0              # Match user's manual settings
MAX_ERRORS_PER_SESSION = 20     # Shutdown if session hit this many errors
