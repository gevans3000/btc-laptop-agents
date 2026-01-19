"""Error classification for exchange API calls."""


class ProviderError(Exception):
    """Base class for all provider-related errors."""


class TransientProviderError(ProviderError):
    """Temporary failures: timeouts, connection errors, maintenance."""


class RateLimitProviderError(ProviderError):
    """HTTP 429 or rate limit exceeded."""


class AuthProviderError(ProviderError):
    """Authentication or permission errors."""


class UnknownProviderError(ProviderError):
    """Unexpected or unclassified errors."""


class SafetyException(Exception):
    """Raised when a hard-coded safety limit is breached."""
