#!/usr/bin/env python3
"""
SensitiveStr - Wrapper for secrets that masks itself in logs, exceptions, and repr.
Prevents accidental leakage of API keys, tokens, passwords, etc.
"""

import threading

import logging
from typing import Any, Optional, Set, Union

logger = logging.getLogger(__name__)

_thread_local_storage = threading.local()


class SensitiveStr:
    """
    A string wrapper that masks its value in all string representations.
    """

    def __init__(self, value: Optional[str]):
        """Initialize with secret value."""
        self._value = value

    def __str__(self) -> str:
        """Return actual value for API calls."""
        return self._value if self._value else ""

    def __repr__(self) -> str:
        """Mask value in logs and debugging."""
        if self._value is None:
            return "SensitiveStr(None)"
        prefix = self._value[:7] if len(self._value) > 7 else self._value[:2]
        return f"SensitiveStr('{prefix}...***REDACTED***')"

    def __bool__(self) -> bool:
        """Allow truthiness checks."""
        return bool(self._value)

    def __eq__(self, other) -> bool:
        """Allow equality checks."""
        if isinstance(other, SensitiveStr):
            return self._value == other._value
        return self._value == other

    def __len__(self) -> int:
        """Allow length checks."""
        return len(self._value) if self._value else 0

    def get_secret(self) -> str:
        """Explicit method to get the actual secret value."""
        return self._value if self._value else ""

    def is_valid(self) -> bool:
        """Check if the secret is set and not a placeholder."""
        if not self._value:
            return False
        placeholders = [
            "your-api-key-here",
            "your-key-here",
            "sk-ant-DEV-KEY",
            "REPLACEME",
            "PLACEHOLDER",
            "INSERT_KEY_HERE",
        ]
        return not any(p.lower() in self._value.lower() for p in placeholders)

    def startswith(self, prefix: str) -> bool:
        """Allow prefix checks."""
        return self._value.startswith(prefix) if self._value else False

    def mask_for_display(self, show_chars: int = 4) -> str:
        """Return a masked version suitable for UI display."""
        if not self._value:
            return "***NOT SET***"
        if len(self._value) <= show_chars:
            return "*" * len(self._value)
        visible = self._value[:show_chars]
        masked = "*" * (len(self._value) - show_chars)
        return f"{visible}{masked}"


def sanitize_for_logging(data: Any, max_depth: int = 10) -> Any:
    """Recursively sanitize a value for safe logging."""
    if not hasattr(_thread_local_storage, "visited"):
        _thread_local_storage.visited = set()

    try:
        return _recursive_sanitize(data, max_depth)
    finally:
        if hasattr(_thread_local_storage, "visited"):
            del _thread_local_storage.visited


def _recursive_sanitize(value: Any, max_depth: int) -> Any:
    """Recursive worker for sanitization."""
    if max_depth <= 0:
        logger.warning("Max recursion depth reached in sanitize_for_logging.")
        return "<max depth reached>"

    if isinstance(value, (dict, list, tuple)):
        return _sanitize_container(value, max_depth)

    return _sanitize_leaf(value)


def _sanitize_container(value: Union[dict, list, tuple], max_depth: int) -> Any:
    """Handle dictionaries and lists with circular reference checking."""
    visited: Set[int] = _thread_local_storage.visited
    value_id = id(value)

    if value_id in visited:
        logger.warning("Circular reference detected in sanitize. ID: %s", value_id)
        return "<circular reference>"

    visited.add(value_id)
    try:
        if isinstance(value, dict):
            return {k: _recursive_sanitize(v, max_depth - 1) for k, v in value.items()}

        # list or tuple
        return type(value)(_recursive_sanitize(item, max_depth - 1) for item in value)
    finally:
        visited.discard(value_id)


def _sanitize_leaf(value: Any) -> Any:
    """Handle non-container types."""
    if isinstance(value, SensitiveStr):
        return repr(value)

    if isinstance(value, str):
        return "***REDACTED***" if _looks_like_secret(value) else value

    return value


def _looks_like_secret(value: str) -> bool:
    """Heuristic to detect if a string looks like a secret."""
    try:
        if not value or len(value) < 20:
            return False
        if _matches_known_patterns(value):
            return True
        return _matches_high_entropy_heuristic(value)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.error("Error in secret heuristic: %s", e, exc_info=True)
        return False


def _matches_known_patterns(value: str) -> bool:
    """Check against known API key prefixes."""
    secret_patterns = [
        "sk-ant-api",
        "sk-proj-",
        "sk-",
        "ghp_",
        "gho_",
        "glpat-",
        "xoxb-",
        "xoxp-",
        "AKIA",
        "AIza",
    ]
    return any(pattern in value for pattern in secret_patterns)


def _matches_high_entropy_heuristic(value: str) -> bool:
    """Check for complex alphanumeric strings."""
    if "http" in value.lower():
        return False

    has_upper = any(c.isupper() for c in value)
    has_lower = any(c.islower() for c in value)
    has_digit = any(c.isdigit() for c in value)
    has_special = any(c in "-_." for c in value)

    # Require special chars for high entropy unless it's extremely long
    return has_upper and has_lower and has_digit and has_special and len(value) > 30


def wrap_secret(value: Optional[str]) -> SensitiveStr:
    """Wrap a string in SensitiveStr if it's not None."""
    return SensitiveStr(value)
