from .base import MonkBaseError


class ProviderError(MonkBaseError):
    """
    Model provider API failures.

    Used when:
    - Network connection fails.
    - API Key is invalid (Auth).
    - Rate limit exceeded (429).
    """

    pass
