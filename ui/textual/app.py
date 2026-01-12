# ui/textual/app.py

import sys
from pathlib import Path

# Add parent directory to path to import agent module (if needed for standalone run)
# Adjust this based on your actual project root relative to this file
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from textual.app import App, ComposeResult
from textual.binding import Binding
from agent.events import get_event_bus
from agent.mock_event_agent import MockEventAgent
from .screens.main_chat import MainChatScreen
from .commands import ProtocolMonkProvider

class ProtocolMonkApp(App):
    """Protocol Monk - The Oracle of the Holy Light"""

    CSS_PATH = [
        "styles/main.tcss",
        "styles/chat.tcss",
        "styles/components.tcss"
    ]

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("ctrl+p", "command_palette", "Commands"),
        Binding("f1", "show_help", "Help"),
    ]

    # ... inside ProtocolMonkApp class ...

    async def call_from_child_submit(self, text: str) -> None:
        """
        Called by InputBar when the user submits a message.
        """
        # 1. Find the ChatArea widget
        chat_area = self.query_one("ChatArea")
        
        # 2. Add the User's message (Right aligned bubble)
        await chat_area.add_user_message(text)

        # 3. Trigger the Agent (Mock logic for now)
        # We will connect the real event bus here in the next step.
        # For now, let's just prove the UI works by echoing a "thinking" state.
        
        status_bar = self.query_one("StatusBar")
        status_bar.status = "Thinking..."
        
        # Simulate a quick response to prove the AI Canvas works
        await chat_area.add_ai_message(f"**Mock Response:** I received your message: *{text}*")
        
        status_bar.status = "Idle"

    # Register the Command Provider
    COMMANDS = App.COMMANDS | {ProtocolMonkProvider}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.event_bus = get_event_bus()
        self.agent = MockEventAgent(self.event_bus)

    def on_mount(self) -> None:
        """Initialize the app."""
        self.push_screen(MainChatScreen())

if __name__ == "__main__":
    app = ProtocolMonkApp()
    app.run()