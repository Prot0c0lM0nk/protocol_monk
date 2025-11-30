# styles.py
from rich.theme import Theme
from rich.console import Console
from rich.style import Style
from rich.panel import Panel
from rich import box

# --- ORTHODOX MATRIX THEME ---
ORTHODOX_MATRIX_THEME = Theme(
    {
        # Base Colors
        "monk.text": "green1",  # The Matrix Green (Main Text)
        "monk.border": "medium_purple1",  # Green Borders
        "holy.gold": "bold #ffaa44",  # Orthodox Gold (Icons/User)
        "tech.cyan": "bold #00d7ff",  # Machine/Tool Color
        # Functional Styles
        "success": "bold #44ff44",  # The specific green you liked
        "dim": "dim #44ff44",  # Faded matrix text
        # Markdown Overrides
        "markdown.paragraph": "green1",
        "markdown.list": "spring_green1",
        "markdown.item": "green1",
        "markdown.code": "green1 on #111111",
    }
)

# The shared console instance
console = Console(theme=ORTHODOX_MATRIX_THEME)


def create_monk_panel(content, title="✠ Monk"):
    """
    Factory function to ensure all Agent panels look identical.
    Used by both the Streamer (rich_ui.py) and the History (message.py).
    """
    return Panel(
        content,
        title=f"[monk.border]{title}[/]",
        title_align="left",
        border_style="monk.border",
        box=box.ROUNDED,
        padding=(1, 2),
        width=100,
    )


def create_task_completion_panel(content, title="✓ Task Complete"):
    """
    Factory function for task completion panels with success styling.
    """
    return Panel(
        content,
        title=f"[success]{title}[/]",
        title_align="left",
        border_style="success",
        box=box.ROUNDED,
        padding=(1, 2),
        width=100,
    )
