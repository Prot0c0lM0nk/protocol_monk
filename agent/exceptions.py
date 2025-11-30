#!/usr/bin/env python3
"""
Base Exception Contract for MonkCode Agent

Provides the single source of truth for the Agent's error contract.
All domain-specific exceptions must inherit from MonkBaseError.
"""

from typing import Any, Dict, Optional


class MonkBaseError(Exception):
    """
    The Base Contract for all Agent errors.
    """

    def __init__(
        self,
        message: str,
        original_error: Optional[Exception] = None,
        user_hint: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.message = message
        self.original_error = original_error
        self.user_hint = user_hint or "An internal error occurred."
        self.details = details or {}


def wrap_exception(exception_class, user_hint=None):
    """
    Decorator that catches generic exceptions and Re-Raises them
    as the specific MonkBaseError subclass.
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Re-raise as the specific exception class
                raise exception_class(
                    message=str(e), original_error=e, user_hint=user_hint
                ) from e

        return wrapper

    return decorator


# Export the base contract
__all__ = ["MonkBaseError", "wrap_exception"]
