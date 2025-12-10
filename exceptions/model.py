#!/usr/bin/env python3
"""
Model Exception Definitions for MonkCode

All model-related exceptions inherit from MonkBaseError.
"""

from exceptions.base import MonkBaseError


class ModelError(MonkBaseError):
    """Base exception for model-related errors."""

    pass


class ModelTimeoutError(ModelError):
    """Raised when model API request times out."""

    def __init__(self, message, timeout_seconds=None, details=None):
        super().__init__(message, details=details)
        self.timeout_seconds = timeout_seconds


class ModelConfigurationError(ModelError):
    """Raised when model configuration is invalid or missing."""

    pass


class EmptyResponseError(ModelError):
    """Raised when model returns an empty response."""

    pass
class ModelClientError(ModelError):
    """Raised when model client initialization or operations fail."""
    pass



class ModelResponseParseError(ModelError):
    """Raised when model response cannot be parsed (e.g., invalid JSON)."""
    
    def __init__(self, message, raw_response=None, original_error=None, details=None):
        super().__init__(message, details=details)
        self.raw_response = raw_response
        self.original_error = original_error
        self.user_hint = "The model returned invalid data. Please try again."


class ModelRateLimitError(ModelError):
    """Raised when Ollama API returns a 429 status."""
    
    def __init__(self, message, retry_after=None, details=None):
        super().__init__(message, details=details)
        self.retry_after = retry_after or 60  # Default to 60 seconds if not specified
        self.user_hint = f"Rate limit exceeded. Retry after {self.retry_after} seconds."