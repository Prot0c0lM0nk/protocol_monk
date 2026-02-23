"""Canonical Textual phase names mapped to current agent states."""

from typing import Final

READY: Final[str] = "idle"
THINKING: Final[str] = "thinking"
EXECUTING: Final[str] = "executing"
PAUSED: Final[str] = "paused"
ERROR: Final[str] = "error"

_ALLOWED: Final[set[str]] = {READY, THINKING, EXECUTING, PAUSED, ERROR}
_ALIASES: Final[dict[str, str]] = {
    "ready": READY,
    "busy": EXECUTING,
}


def normalize_phase(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in _ALLOWED:
        return text
    return _ALIASES.get(text, READY)
