#!/usr/bin/env python3
"""
Context Exception Definitions for MonkCode

All context-related exceptions inherit from MonkBaseError.
"""

from typing import Any

from exceptions.base import MonkBaseError
"""
Context Exception Definitions for MonkCode

All context-related exceptions inherit from MonkBaseError.
"""

from exceptions.base import MonkBaseError


class ContextError(MonkBaseError):
    """Base exception for context management errors."""

    pass


class ContextOverflowError(ContextError):
    """Raised when context token limit is exceeded."""

    def __init__(self, message, current_tokens=None, max_tokens=None):
        super().__init__(message)
        self.current_tokens = current_tokens
        self.max_tokens = max_tokens


class ContextCorruptionError(ContextError):
    """Raised when context data structure is corrupted."""

    def __init__(self, message, corruption_type=None):
        super().__init__(message)
        self.corruption_type = corruption_type



class ContextValidationError(ContextError):
    """Raised when context validation fails."""

    def __init__(
        self, message: str, validation_type: str = None, invalid_value: Any = None
    ):
        super().__init__(message)
        self.validation_type = validation_type
        self.invalid_value = invalid_value


class TokenEstimationError(ContextError):
    """Raised when token estimation fails due to estimator issues."""

    def __init__(
        self,
        message: str,
        estimator_name: str = None,
        failed_text: str = None,
        original_error: Exception = None,
    ):
        super().__init__(message)
        self.estimator_name = estimator_name
        self.failed_text = failed_text
        self.original_error = original_error


class NeuralSymIntegrationError(ContextError):
    """Raised when NeuralSym enhancement or recording fails."""

    def __init__(
        self,
        message: str,
        operation: str = None,
        original_error: Exception = None,
    ):
        super().__init__(message)
        self.operation = operation
        self.original_error = original_error
