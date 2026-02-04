"""
ui/common.py
Shared visual utilities for consistency across UI modes.
Handles error formatting and message improvement.
"""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box

# --- ERROR TRANSLATION LAYER ---
ERROR_HINTS = {
    "FileNotFound": "I cannot locate that file. Please verify the path exists.",
    "ConnectionRefused": "I could not connect to the server. Is the local LLM running?",
    "rate_limit": "The API provider is rate-limiting us. Please wait a moment.",
    "context_length": "The file is too large for the model's context window.",
    "KeyError": "Internal Data Error: Missing expected key in tool output.",
    "KeyboardInterrupt": "User cancelled the operation.",
}


def _improve_error_message(raw_msg: str) -> str:
    """
    Check generic error strings and append helpful hints.
    """
    msg_str = str(raw_msg)

    # 1. Check for specific keywords in the error message
    for key, hint in ERROR_HINTS.items():
        if key.lower() in msg_str.lower():
            # Returns: "Original Error\nHint: Helpful explanation"
            return f"{msg_str}\n\n[dim italic]Hint: {hint}[/]"

    # 2. Return original if no hints found
    return msg_str


# --- SHARED RENDERER ---
def render_shared_error(console: Console, message: str, use_panel: bool = False):
    """
    Unified error display with auto-improvement.

    Args:
        console: The rich console to print to.
        message: The error message string.
        use_panel: If True, wraps in a 'System Failure' panel (Rich Mode).
                   If False, prints formatted text (Plain Mode).
    """
    # Translate / Improve the message
    clean_message = _improve_error_message(message)

    if use_panel:
        # RICH MODE: The Matrix 'System Failure' Box
        # We parse markup so the [dim] tags in our hints work
        content = Text.from_markup(clean_message, style="red3 bold")

        panel = Panel(
            content,
            title="[bold red]⚠️ System Exception[/]",
            border_style="red3",
            box=box.ROUNDED,
            padding=(1, 2),
        )
        console.print(panel)
    else:
        # PLAIN MODE: Clear, bold red text
        console.print()
        console.print(f"[bold red]❌ ERROR:[/bold red] {clean_message}")
        console.print()
