"""Textual model layer."""

from .detail_record import DetailRecord
from .phase_state import (
    ALLOWED_PHASES,
    PHASE_ACTIVE_FLAGS,
    PHASE_LABELS,
    PHASE_STYLE_CLASS,
    READY,
    THINKING,
    PLANNING,
    RUNNING_TOOLS,
    AWAITING_APPROVAL,
    WAITING_INPUT,
    ERROR,
    normalize_phase,
)

__all__ = [
    "DetailRecord",
    "ALLOWED_PHASES",
    "PHASE_ACTIVE_FLAGS",
    "PHASE_LABELS",
    "PHASE_STYLE_CLASS",
    "READY",
    "THINKING",
    "PLANNING",
    "RUNNING_TOOLS",
    "AWAITING_APPROVAL",
    "WAITING_INPUT",
    "ERROR",
    "normalize_phase",
]
