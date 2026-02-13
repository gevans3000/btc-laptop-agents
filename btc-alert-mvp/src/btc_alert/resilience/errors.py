class ProviderError(Exception):
    """Base class for collector/provider errors."""


class TransientProviderError(ProviderError):
    """Temporary failures: timeout, 5xx, network hiccups."""


class RateLimitProviderError(ProviderError):
    """Rate limit exceeded."""


class UnknownProviderError(ProviderError):
    """Unexpected collector failure."""
