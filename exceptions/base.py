from typing import Optional, Dict, Any


class MonkBaseError(Exception):
    """
    Base class for all Protocol Monk errors.

    Design Philosophy:
    - user_hint: A safe, readable message to show the end-user (UI).
    - details: Technical metadata for the debug log (UUIDs, paths, etc).
    """

    def __init__(
        self,
        message: str,
        user_hint: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.user_hint = user_hint or message
        self.details = details or {}
