"""
ui/textual/screens/modals/quit_confirm_screen.py
Modal dialog for confirming quit
"""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button


class QuitConfirmScreen(ModalScreen[bool]):
    """
    Modal screen for quit confirmation
    Returns True if confirmed, False if cancelled
    """

    BINDINGS = [
        ("y", "confirm", "Yes"),
        ("n", "cancel", "No"),
        ("escape", "cancel", "Cancel"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the quit confirmation dialog"""
        with Vertical(id="dialog"):
            yield Static("Are you sure you want to quit?", id="title")
            with Horizontal(id="buttons"):
                yield Button("Yes (Y)", variant="error", id="yes")
                yield Button("No (N)", variant="primary", id="no")

    def action_confirm(self) -> None:
        """Confirm quit"""
        self.dismiss(True)

    def action_cancel(self) -> None:
        """Cancel quit"""
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "yes":
            self.action_confirm()
        elif event.button.id == "no":
            self.action_cancel()