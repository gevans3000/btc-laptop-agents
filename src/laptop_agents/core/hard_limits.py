"""
Hard-coded safety limits that cannot be overridden by user configuration.
Acting as a 'hardware' ceiling for the trading agents.
"""

MAX_POSITION_SIZE_USD = 50000.0  # Absolute max for any single trade
MAX_DAILY_LOSS_USD = 50.0       # Halt if we lose this much in today's runs
MIN_RR_RATIO = 1.0              # Reject trades with R:R below this
MAX_LEVERAGE = 20.0              # Match user's manual settings
