from textual.app import App
from textual.screen import Screen
from textual.containers import Container
from textual.widgets import Label
from textual import on
from ui.textual.interface import TextualUI
from ui.textual.screens.chat import ChatScreen
from ui.textual.screens.approval import ApprovalScreen
from agent.core import ProtocolAgent


class MonkCodeTUI(App):
    """Main application for Textual TUI."""
    CSS_PATH = "styles.tcss"
    SCREENS = {
        "chat": ChatScreen,
        "approval": ApprovalScreen,
    }

    def __init__(self, agent):
        super().__init__()
        self.agent = agent
        self.ui = None

    def on_mount(self):
        """Initialize the UI and push the main screen."""
        self.ui = TextualUI(self)
        self.agent.ui = self.ui  # Inject UI into agent
        self.push_screen("chat")

    def on_exit(self):
        """Clean up resources on exit."""
        if self.ui:
            self.ui = None
        if self.agent:
            self.agent.close()