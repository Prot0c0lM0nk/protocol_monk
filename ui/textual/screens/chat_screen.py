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
        # FIX: Call the custom method 'write_to_log', not 'write'
        self.query_one(ChatDisplay).write_to_log(text)

    # --- New Methods for Status Updates ---

    def show_loading_indicator(self):
        """Optional: Could show a spinner. For now, do nothing."""
        pass

    def finalize_response(self):
        """Tell display the stream is done."""
        self.query_one(ChatDisplay).end_current_message()

    async def on_chat_input_submitted(self, message: ChatInput.Submitted):
        """
        When user hits Enter:
        1. Show user message in display
        2. Resolve the Future so the Agent gets the input
        """
        display = self.query_one(ChatDisplay)
        display.add_user_message(message.value)
        
        # Notify the App (Container) that we have input for the Agent
        await self.app.resolve_input(message.value)