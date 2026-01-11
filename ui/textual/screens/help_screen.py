"""
ui/textual/screens/help_screen.py
Help screen with instructions
"""
from textual.app import ComposeResult
from textual.screen import Screen
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Static, Button, Label

class HelpScreen(Screen):
    """
    Help screen
    Show keyboard shortcuts and usage instructions
    """

    BINDINGS = [
        ("escape", "app.switch_mode('chat')", "Back"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the help screen"""
        yield Header()
        with Vertical():
            yield Static("Help", id="title")
            yield Static(
                """Keyboard Shortcuts:
                
Ctrl+C - Quit
Ctrl+S - Settings
Ctrl+H - Help
Escape - Back to Chat

Type your message and press Enter to send.
""",
                id="content"
            )
            with Horizontal(id="buttons"):
                yield Button("Back", variant="primary", id="back")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "back":
            self.app.switch_mode("chat")