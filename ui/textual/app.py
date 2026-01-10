from textual.app import App
from textual.screen import Screen
from ui.textual.screens import ChatScreen
from ui.textual.interface import TextualUI


class ProtocolMonkApp(App):
    """
    Main Textual Application for Protocol Monk.
    """

    CSS_PATH = "styles.tcss"
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+d", "toggle_dark", "Toggle Dark Mode"),
    ]

    # We will inject the controller (TextualUI) after instantiation
    controller: "TextualUI" = None

    def on_mount(self) -> None:
        """
        Called when the app is mounted.
        Push the main ChatScreen immediately.
        """
        self.push_screen(ChatScreen())

    def handle_user_input(self, text: str) -> None:
        """
        Called by ChatScreen when user submits text.
        Passes the text to the waiting Agent via the Controller.
        """
        if self.controller:
            self.controller.input_queue.put_nowait(text)
        else:
            self.notify("Error: Controller not connected", severity="error")

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark
