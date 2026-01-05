"""Error classification for exchange API calls."""

class ProviderError(Exception):
    """Base class for all provider-related errors."""
    pass

class TransientProviderError(ProviderError):
    """Temporary failures: timeouts, connection errors, maintenance."""
    pass

class RateLimitProviderError(ProviderError):
    """HTTP 429 or rate limit exceeded."""
    pass

class AuthProviderError(ProviderError):
    """Authentication or permission errors."""
    pass

class UnknownProviderError(ProviderError):
    """Unexpected or unclassified errors."""
    pass
