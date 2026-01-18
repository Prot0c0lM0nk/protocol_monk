"""
MonkCode Utilities Exception Definitions.
"""


class MonkUtilError(Exception):
    """Base exception for utility modules. No dependency on Agent."""


class JsonParsingError(MonkUtilError):
    """Raised when JSON parsing fails (replacing silent failures)."""

    def __init__(self, message, original_error=None, partial_data=None, position=None):
        super().__init__(message)
        self.original_error = original_error
        self.partial_data = partial_data
        self.position = position
        self.message = message


class ContextError(MonkUtilError):
    """Raised when context-related operations fail."""


class ConfigurationError(MonkUtilError):
    """Raised when configuration is invalid or missing."""
