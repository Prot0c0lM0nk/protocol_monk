import logging
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


def exception_user_hint(
    exc: BaseException,
    *,
    fallback: str = "An unexpected error occurred.",
) -> str:
    if isinstance(exc, MonkBaseError):
        hint = str(exc.user_hint or "").strip()
        if hint:
            return hint
    text = str(exc).strip()
    return text or fallback


def exception_details(exc: BaseException) -> Dict[str, Any]:
    if isinstance(exc, MonkBaseError):
        return dict(exc.details or {})
    return {}


def log_exception(
    logger: logging.Logger,
    level: int,
    summary: str,
    exc: BaseException,
) -> None:
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logger.log(level, "%s: %s", summary, exc, exc_info=True)
    else:
        logger.log(level, "%s: %s", summary, exc)
