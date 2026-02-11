"""
ui/textual/models/phase_state.py
Canonical phase registry for Textual UI runtime state.
"""

from typing import Final, Literal

READY: Final[str] = "ready"
THINKING: Final[str] = "thinking"
PLANNING: Final[str] = "planning"
RUNNING_TOOLS: Final[str] = "running_tools"
AWAITING_APPROVAL: Final[str] = "awaiting_approval"
WAITING_INPUT: Final[str] = "waiting_input"
ERROR: Final[str] = "error"

PhaseName = Literal[
    "ready",
    "thinking",
    "planning",
    "running_tools",
    "awaiting_approval",
    "waiting_input",
    "error",
]

ALLOWED_PHASES: Final[tuple[str, ...]] = (
    READY,
    THINKING,
    PLANNING,
    RUNNING_TOOLS,
    AWAITING_APPROVAL,
    WAITING_INPUT,
    ERROR,
)

PHASE_LABELS: Final[dict[str, str]] = {
    READY: "Ready",
    THINKING: "Thinking",
    PLANNING: "Planning",
    RUNNING_TOOLS: "Running Tools",
    AWAITING_APPROVAL: "Awaiting Approval",
    WAITING_INPUT: "Waiting for Input",
    ERROR: "Error",
}

PHASE_ACTIVE_FLAGS: Final[dict[str, bool]] = {
    READY: False,
    THINKING: True,
    PLANNING: True,
    RUNNING_TOOLS: True,
    AWAITING_APPROVAL: True,
    WAITING_INPUT: False,
    ERROR: False,
}

PHASE_STYLE_CLASS: Final[dict[str, str]] = {
    READY: "status-ready",
    THINKING: "status-thinking",
    PLANNING: "status-planning",
    RUNNING_TOOLS: "status-tools",
    AWAITING_APPROVAL: "status-waiting",
    WAITING_INPUT: "status-waiting",
    ERROR: "status-error",
}


def normalize_phase(value: str) -> str:
    """Return a valid phase key or READY as fallback."""
    if value in ALLOWED_PHASES:
        return value
    return READY
