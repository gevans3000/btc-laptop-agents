"""Typed exception hierarchy for trading operations."""


class TradingException(Exception):
    """Base for all trading-related errors."""


class PositionError(TradingException):
    """Errors related to position management."""


class PersistenceError(TradingException):
    """Errors saving/loading state."""


class OrderRejectedError(TradingException):
    """Order rejected by risk checks."""


class BrokerConnectionError(TradingException):
    """Connection to broker failed."""
