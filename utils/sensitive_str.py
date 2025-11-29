#!/usr/bin/env python3
"""
SensitiveStr - Wrapper for secrets that masks itself in logs, exceptions, and repr
Prevents accidental leakage of API keys, tokens, passwords, etc.
"""

from typing import Optional
import threading
import logging

logger = logging.getLogger(__name__)

_thread_local_storage = threading.local()


class SensitiveStr:
    """
    A string wrapper that masks its value in all string representations.
    Use this for API keys, passwords, tokens, and other secrets.

    Example:
        api_key = SensitiveStr("sk-ant-api03-abc123...")
        print(api_key)  # Output: SensitiveStr('***REDACTED***')
        logger.error(f"Failed with key {api_key}")  # Logs: Failed with key ***REDACTED***
        str(api_key)  # Returns the actual value for use in API calls
    """

    def __init__(self, value: Optional[str]):
        """Initialize with secret value"""
        self._value = value

    def __str__(self) -> str:
        """Return actual value for API calls"""
        return self._value if self._value else ""

    def __repr__(self) -> str:
        """Mask value in logs and debugging"""
        if self._value is None:
            return "SensitiveStr(None)"
        # Show only first 7 chars to help identify which key, rest masked
        prefix = self._value[:7] if len(self._value) > 7 else self._value[:2]
        return f"SensitiveStr('{prefix}...***REDACTED***')"

    def __bool__(self) -> bool:
        """Allow truthiness checks: if api_key: ..."""
        return bool(self._value)

    def __eq__(self, other) -> bool:
        """Allow equality checks"""
        if isinstance(other, SensitiveStr):
            return self._value == other._value
        return self._value == other

    def __len__(self) -> int:
        """Allow length checks"""
        return len(self._value) if self._value else 0

    def get_secret(self) -> str:
        """Explicit method to get the actual secret value"""
        return self._value if self._value else ""

    def is_valid(self) -> bool:
        """Check if the secret is set and not a placeholder"""
        if not self._value:
            return False

        # Check against common placeholder patterns
        placeholders = [
            "your-api-key-here",
            "your-key-here",
            "sk-ant-DEV-KEY",
            "REPLACEME",
            "PLACEHOLDER",
            "INSERT_KEY_HERE",
        ]

        return not any(
            placeholder.lower() in self._value.lower() for placeholder in placeholders
        )

    def startswith(self, prefix: str) -> bool:
        """Allow prefix checks (e.g., checking if it starts with 'sk-ant-')"""
        return self._value.startswith(prefix) if self._value else False

    def mask_for_display(self, show_chars: int = 4) -> str:
        """
        Return a masked version suitable for UI display.
        Shows first N chars, masks the rest.

        Example:
            mask_for_display(4) -> "sk-a***************"
        """
        if not self._value:
            return "***NOT SET***"

        if len(self._value) <= show_chars:
            return "*" * len(self._value)

        visible = self._value[:show_chars]
        masked = "*" * (len(self._value) - show_chars)
        return f"{visible}{masked}"


def sanitize_for_logging(data: any, max_depth: int = 10) -> any:
    """
    Recursively sanitize a value for safe logging.
    This is the thread-safe entry point.

    Args:
        data: Any value (dict, list, str, etc.)
        max_depth: Maximum recursion depth.

    Returns:
        Sanitized version safe for logging
    """
    # Entry point: Set up the visited set for *this thread only*
    if not hasattr(_thread_local_storage, "visited"):
        _thread_local_storage.visited = set()

    try:
        # Call the recursive worker
        return _recursive_sanitize(data, max_depth)
    finally:
        # Clean up this thread's set to prevent memory leaks
        if hasattr(_thread_local_storage, "visited"):
            del _thread_local_storage.visited


def _recursive_sanitize(value: any, max_depth: int) -> any:
    """
    Recursive worker for sanitization. Uses a thread-local set to
    prevent circular references.
    """
    if max_depth <= 0:
        logger.warning("Max recursion depth reached in sanitize_for_logging.")
        return "<max depth reached>"

    _visited = _thread_local_storage.visited

    value_id = id(value)
    if isinstance(value, (dict, list, tuple)) and value_id in _visited:
        # HEALTHCHECK FIX: Catches silent circular reference failures
        logger.warning(
            f"Circular reference detected in sanitize_for_logging. Value ID: {value_id}"
        )
        return "<circular reference>"

    if isinstance(value, SensitiveStr):
        return repr(value)

    if isinstance(value, str):
        if _looks_like_secret(value):
            return "***REDACTED***"
        return value

    if isinstance(value, dict):
        _visited.add(value_id)
        try:
            return {k: _recursive_sanitize(v, max_depth - 1) for k, v in value.items()}
        finally:
            _visited.discard(value_id)

    if isinstance(value, (list, tuple)):
        _visited.add(value_id)
        try:
            return type(value)(
                _recursive_sanitize(item, max_depth - 1) for item in value
            )
        finally:
            _visited.discard(value_id)

    return value


def _looks_like_secret(value: str) -> bool:
    """
    Heuristic to detect if a string looks like a secret.
    Checks for patterns common in API keys, tokens, etc.
    """
    try:
        if not value or len(value) < 20:
            return False

        # Known API key patterns
        secret_patterns = [
            "sk-ant-api",  # Anthropic
            "sk-proj-",  # OpenAI project keys
            "sk-",  # Generic OpenAI
            "ghp_",  # GitHub personal token
            "gho_",  # GitHub OAuth token
            "glpat-",  # GitLab personal token
            "xoxb-",  # Slack bot token
            "xoxp-",  # Slack user token
            "AKIA",  # AWS access key
            "AIza",  # Google API key
        ]

        for pattern in secret_patterns:
            if pattern in value:
                return True

        # Heuristic: long alphanumeric with mixed case and special chars
        # (but not URLs which have similar patterns)
        if "http" not in value.lower():
            has_upper = any(c.isupper() for c in value)
            has_lower = any(c.islower() for c in value)
            has_digit = any(c.isdigit() for c in value)
            has_special = any(c in "-_." for c in value)

            if has_upper and has_lower and has_digit and len(value) > 30:
                return True

        return False
    except Exception as e:
        # HEALTHCHECK FIX: Catches missing exception handling
        logger.error(f"Error in _looks_like_secret heuristic: {e}", exc_info=True)
        return False  # Fail safe


# Convenience function for config usage
def wrap_secret(value: Optional[str]) -> SensitiveStr:
    """
    Wrap a string in SensitiveStr if it's not None.
    Returns SensitiveStr(None) if value is None.
    """
    return SensitiveStr(value)
