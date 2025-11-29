class MonkUtilError(Exception):
    """Base exception for utility modules. No dependency on Agent."""

    pass


class JsonParsingError(MonkUtilError):
    """Raised when JSON parsing fails (replacing silent failures)."""

    def __init__(self, message, original_error=None, partial_data=None):
        super().__init__(message)
        self.original_error = original_error
        self.partial_data = partial_data


class ContextError(MonkUtilError):
    """Raised when context-related operations fail."""

    pass


class ConfigurationError(MonkUtilError):
    """Raised when configuration is invalid or missing."""

    pass
