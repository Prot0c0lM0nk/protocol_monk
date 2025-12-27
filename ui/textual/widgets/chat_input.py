from textual.widgets import Input
from textual.message import Message

class ChatInput(Input):
    """
    Custom Input widget that emits a structured message on submit.
    """
    
    class Submitted(Message):
        """Event sent when user hits Enter."""
        def __init__(self, value: str):
            self.value = value
            super().__init__()

    def on_mount(self):
        self.placeholder = "Enter command or message..."

    async def action_submit(self):
        """Override default submit to clear input automatically."""
        value = self.value
        if value.strip():
            # Clear first, then post message
            self.value = ""
            self.post_message(self.Submitted(value))