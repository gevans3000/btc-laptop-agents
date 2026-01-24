"""Typed exception hierarchy for trading operations."""


class TradingException(Exception):
    """Base for all trading-related errors."""

    pass


class PositionError(TradingException):
    """Errors related to position management."""

    pass


class PersistenceError(TradingException):
    """Errors saving/loading state."""

    pass


class OrderRejectedError(TradingException):
    """Order rejected by risk checks."""

    pass


class BrokerConnectionError(TradingException):
    """Connection to broker failed."""

    pass
