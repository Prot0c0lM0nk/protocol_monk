from .base import MonkBaseError


class ConfigError(MonkBaseError):
    """
    Configuration or startup failure.

    Used when:
    - Required environment variables are missing.
    - system_prompt.txt cannot be read.
    - JSON settings are malformed.
    """

    pass
