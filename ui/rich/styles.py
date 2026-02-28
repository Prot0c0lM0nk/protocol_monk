"""Shared Rich styling for the runtime Rich UI."""

from __future__ import annotations

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.style import Style
from rich.theme import Theme

RICH_THEME = Theme(
    {
        "agent.text": "bright_white",
        "agent.border": "bright_cyan",
        "thinking": "grey70 italic",
        "tool": Style(color="yellow", bold=True),
        "success": Style(color="green", bold=True),
        "error": Style(color="red", bold=True),
        "warning": Style(color="dark_orange", bold=True),
        "info": Style(color="cyan", bold=True),
        "muted": "grey50",
        "state.idle": "green",
        "state.thinking": "yellow",
        "state.executing": "cyan",
        "state.paused": "magenta",
        "state.error": "red",
    }
)

console = Console(theme=RICH_THEME)


def panel(content, *, title: str, border_style: str = "agent.border") -> Panel:
    """Create a standard rounded panel for Rich UI output."""
    return Panel(
        content,
        title=title,
        title_align="left",
        border_style=border_style,
        box=box.ROUNDED,
        padding=(0, 1),
    )


def state_style(status: str) -> str:
    normalized = (status or "idle").strip().lower()
    return {
        "idle": "state.idle",
        "thinking": "state.thinking",
        "executing": "state.executing",
        "paused": "state.paused",
        "error": "state.error",
    }.get(normalized, "muted")
