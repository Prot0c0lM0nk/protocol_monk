"""
ui/rich/styles.py
The Definitive 'Orthodox Matrix' Theme Definition.
"""

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.style import Style
from rich.theme import Theme

# --- 1. THE DEFINITIVE PALETTE (From User Spec) ---
ORTHODOX_MATRIX_THEME = Theme(
    {
        # Base Colors
        "monk.text": "chartreuse1",  # #87ff00
        "monk.border": "medium_purple3",  # #875fd7
        "user.text": "bright_black",  # Grey (Subtle)
        # Machinery / Tools
        "tech.cyan": Style(color="turquoise2", bold=True),  # #00d7ff
        # Functional Status
        "success": "bright_green",
        "error": Style(color="red3", bold=True),  # #d70000
        "warning": Style(color="gold1", bold=True),  # #ffd700
        "dim": "chartreuse3",  # #5fd700 (Faded reasoning)
        # Markdown Overrides (Mapping to our Palette)
        "markdown.paragraph": "chartreuse1",
        "markdown.list": "chartreuse3",
        "markdown.item": "chartreuse1",
        "markdown.code": "chartreuse1 on #111111",  # Slight background for code
        "markdown.h1": Style(color="medium_purple3", bold=True),
    }
)

# The global console instance
console = Console(theme=ORTHODOX_MATRIX_THEME)

# --- 2. COMPONENT FACTORIES ---


def create_monk_panel(content, title="✠ Monk"):
    """Standard output frame."""
    return Panel(
        content,
        title=f"[monk.border]{title}[/]",
        title_align="left",
        border_style="monk.border",
        box=box.ROUNDED,
        padding=(1, 2),
    )


def create_task_completion_panel(content, title="✓ Task Complete"):
    """Success notification frame."""
    return Panel(
        content,
        title=f"[success]{title}[/]",
        title_align="left",
        border_style="success",
        box=box.ROUNDED,
        padding=(1, 2),
    )
