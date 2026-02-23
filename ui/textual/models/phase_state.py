"""Canonical Textual phase names mapped to current agent states."""

from typing import Final

READY: Final[str] = "idle"
THINKING: Final[str] = "thinking"
EXECUTING: Final[str] = "executing"
PAUSED: Final[str] = "paused"
ERROR: Final[str] = "error"

_ALLOWED: Final[set[str]] = {READY, THINKING, EXECUTING, PAUSED, ERROR}


def normalize_phase(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in _ALLOWED:
        return text
    if "think" in text:
        return THINKING
    if "exec" in text or "tool" in text:
        return EXECUTING
    if "pause" in text or "wait" in text:
        return PAUSED
    if "error" in text or "fail" in text:
        return ERROR
    return READY
