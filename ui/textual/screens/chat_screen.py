"""
ui/textual/screens/chat_screen.py
"""
from textual.screen import Screen
from textual.app import ComposeResult
from ui.textual.widgets.chat_input import ChatInput
from ui.textual.widgets.chat_display import ChatDisplay

class ChatScreen(Screen):
    """
    The Main Interface Screen.
    """
    
    def compose(self) -> ComposeResult:
        yield ChatDisplay()
        yield ChatInput()

    def on_mount(self):
        # Focus input immediately on startup
        self.focus_input()

    # --- THIS WAS MISSING ---
    def focus_input(self):
        """Helper to ensure the input box is selected."""
        self.query_one(ChatInput).focus()
    # ------------------------

    def write_to_log(self, text: str):
        """Called by App to stream text to display."""
        self.query_one(ChatDisplay).write(text)

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