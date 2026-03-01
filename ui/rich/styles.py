"""Shared Rich styling for the runtime Rich UI.

Implements the 'Orthodox Matrix' theme - a distinctive green-on-black terminal aesthetic
with purple accents for interactive elements.
"""

from __future__ import annotations

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.style import Style
from rich.theme import Theme
from prompt_toolkit.styles import Style as PtStyle

# --- THE ORTHODOX MATRIX PALETTE ---
ORTHODOX_MATRIX_THEME = Theme(
    {
        # Base Colors - Monk (Agent) output
        "monk.text": "chartreuse1",  # #87ff00 - Primary agent text
        "monk.border": "medium_purple3",  # #875fd7 - Interactive borders
        "user.text": "bright_black",  # Grey (Subtle) - User input
        # Machinery / Tools
        "tech.cyan": Style(color="turquoise2", bold=True),  # #00d7ff
        "tool": Style(color="yellow", bold=True),
        # Functional Status
        "success": "bright_green",
        "error": Style(color="red3", bold=True),  # #d70000
        "warning": Style(color="gold1", bold=True),  # #ffd700
        "info": Style(color="cyan", bold=True),
        # Thinking/Reasoning - dimmed for distinction
        "thinking": Style(color="chartreuse3", italic=True),  # #5fd700 - Faded reasoning
        "dim": "chartreuse3",  # #5fd700 - General dimmed text
        "muted": "grey50",
        # State indicators (for status display)
        "state.idle": "green",
        "state.thinking": "yellow",
        "state.executing": "cyan",
        "state.paused": "magenta",
        "state.error": "red",
        # Markdown Overrides - Map to our Palette
        "markdown.paragraph": "chartreuse1",
        "markdown.list": "chartreuse3",
        "markdown.item": "chartreuse1",
        "markdown.code": "chartreuse1 on #111111",  # Slight background for code
        "markdown.h1": Style(color="medium_purple3", bold=True),
        # Agent text (legacy alias)
        "agent.text": "chartreuse1",
        "agent.border": "medium_purple3",
    }
)

# The global console instance
console = Console(theme=ORTHODOX_MATRIX_THEME)

# Concrete style objects for use in Text widgets (theme names don't resolve in nested renderables)
THINKING_STYLE = Style(color="grey70", italic=True)  # Grey italic for reasoning


def panel(content, *, title: str, border_style: str = "monk.border") -> Panel:
    """Create a standard rounded panel for Rich UI output."""
    return Panel(
        content,
        title=title,
        title_align="left",
        border_style=border_style,
        box=box.ROUNDED,
        padding=(0, 1),
    )


def create_monk_panel(content, title: str = "✠ Monk") -> Panel:
    """Create a standard monk output frame with the Orthodox Matrix styling."""
    return Panel(
        content,
        title=f"[monk.border]{title}[/]",
        title_align="left",
        border_style="monk.border",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def state_style(status: str) -> str:
    """Map status strings to theme style names."""
    normalized = (status or "idle").strip().lower()
    return {
        "idle": "state.idle",
        "thinking": "state.thinking",
        "executing": "state.executing",
        "paused": "state.paused",
        "error": "state.error",
    }.get(normalized, "muted")


# --- PROMPT-TOOLKIT DIALOG STYLE ---
# Orthodox Matrix theme for prompt-toolkit dialogs (button_dialog, radiolist_dialog, etc.)
# Dark green highlight (#1a3a00) allows bright text to show clearly
ORTHODOX_DIALOG_STYLE = PtStyle.from_dict(
    {
        # Dialog container - dark background
        "dialog": "bg:#0a0a0a",
        "dialog.body": "bg:#0a0a0a #87ff00",  # chartreuse1 text
        # Frame/border - purple accents
        "frame.border": "#875fd7",  # medium_purple3
        "frame.label": "#875fd7 bold",  # Purple title
        # Buttons - dark green highlight for focused state
        "button": "#875fd7",
        "button.focused": "bg:#1a3a00 #87ff00 bold",  # Dark green bg, chartreuse text
        "button.arrow": "#87ff00",  # Chartreuse arrow
        # Labels and text
        "label": "#87ff00",
        "shadow": "bg:#1a1a1a",
        # Radio list (for select_with_arrows)
        "radio-list": "bg:#0a0a0a",
        "radio": "#875fd7",
        "radio-selected": "bg:#1a3a00 #87ff00 bold",  # Dark green bg for selected item
        "radio-checked": "#87ff00",
        # Menu/selection highlight (for dropdown-like selections)
        "menu": "bg:#0a0a0a",
        "menu.border": "#875fd7",
        "menu.border.shadow": "bg:#1a1a1a",
        "menu.item": "#87ff00",
        "menu.item.focused": "bg:#1a3a00 #87ff00 bold",  # Dark green highlight
    }
)