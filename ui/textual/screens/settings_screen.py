"""
ui/textual/screens/settings_screen.py
Settings screen for configuration
"""
from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Static, Button, Label

class SettingsScreen(Screen):
    """
    Settings screen
    Configure agent settings
    """

    BINDINGS = [
        ("escape", "app.switch_mode('chat')", "Back"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the settings screen"""
        yield Header()
        with Vertical():
            yield Static("Settings", id="title")
            yield Static("Settings configuration coming soon...", id="content")
            with Horizontal(id="buttons"):
                yield Button("Back", variant="primary", id="back")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "back":
            self.app.switch_mode("chat")