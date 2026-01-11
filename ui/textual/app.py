"""
ui/textual/app.py
Main Textual App for Protocol Monk
"""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from textual.containers import Vertical, Horizontal
from textual.screen import Screen

from .screens.chat_screen import ChatScreen
from .screens.settings_screen import SettingsScreen
from .screens.help_screen import HelpScreen
from .screens.modals.tool_confirm_screen import ToolConfirmScreen
from .screens.modals.quit_confirm_screen import QuitConfirmScreen
from .widgets.chat_display import ChatDisplay
from .widgets.chat_input import ChatInput
from .widgets.status_bar import StatusBar
from agent.events import get_event_bus


class TextualUI(App):
    """
    Main Textual App for Protocol Monk
    ChatGPT-like terminal agent interface
    """

    CSS_PATH = "styles/main.tcss"

    # Screen modes
    MODES = {
        "chat": ChatScreen,
        "settings": SettingsScreen,
        "help": HelpScreen,
    }
    DEFAULT_MODE = "chat"

    # Modal screens
    SCREENS = {
        "tool_confirm": ToolConfirmScreen,
        "quit_confirm": QuitConfirmScreen,
    }

    # Key bindings
    BINDINGS = [
        ("ctrl+c", "request_quit", "Quit"),
        ("ctrl+s", "switch_mode('settings')", "Settings"),
        ("ctrl+h", "switch_mode('help')", "Help"),
        ("escape", "switch_mode('chat')", "Chat"),
    ]

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._setup_event_listeners()

    def _setup_event_listeners(self):
        """Subscribe to agent event bus"""
        # TODO: Set up event listeners for agent events
        pass

    def on_mount(self) -> None:
        """Called when app is mounted"""
        self.switch_mode("chat")

    def action_request_quit(self) -> None:
        """Show quit confirmation dialog"""
        self.push_screen("quit_confirm")

    # TODO: Add agent event handlers
    # async def _on_stream_chunk(self, data: Dict[str, Any]):
    #     pass

    # TODO: Add worker for agent processing
    # @work(exclusive=True, exit_on_error=False)
    # async def process_agent_request(self, user_input: str) -> None:
    #     pass