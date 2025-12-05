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
