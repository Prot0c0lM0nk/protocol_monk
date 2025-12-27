"""
ui/textual/screens/chat_screen.py
"""

from textual.containers import Container
from textual.app import ComposeResult
from ui.textual.widgets.chat_input import ChatInput
from ui.textual.widgets.chat_display import ChatDisplay


class ChatScreen(Container):
    """
    The Main Interface Container.
    """

    def compose(self) -> ComposeResult:
        yield ChatDisplay()
        yield ChatInput()

    def on_mount(self):
        # Focus input immediately on startup
        self.focus_input()

    def focus_input(self):
        """Helper to ensure the input box is selected."""
        # Query the TextArea inside the composite ChatInput widget
        self.query_one("ChatInput TextArea").focus()

    def write_to_log(self, text: str):
        """Called by App to stream text to display."""
        self.query_one(ChatDisplay).write_to_log(text)

    # --- Status Methods ---

    def show_loading_indicator(self):
        pass

    def finalize_response(self):
        self.query_one(ChatDisplay).end_current_message()

    # --- THE FIX IS HERE ---
    async def on_chat_input_submitted(self, message: ChatInput.Submitted):
        """
        When user hits Enter:
        1. Show user message in display
        2. Pass input to the App
        """
        display = self.query_one(ChatDisplay)
        display.add_user_message(message.value)

        # FIX: Remove 'await'. resolve_input is synchronous.
        self.app.resolve_input(message.value)
