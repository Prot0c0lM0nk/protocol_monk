"""
ui/textual/widgets/chat_input.py
Input widget for user messages
"""

from textual.widgets import Input
from textual.message import Message


class ChatInput(Input):
    """
    Chat input widget
    Handles user message input and submission
    """

    class UserSubmitted(Message):
        """Message posted when user submits input"""
        def __init__(self, value: str, input_widget: "ChatInput") -> None:
            self.value = value
            self.input_widget = input_widget
            super().__init__()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """
        Handle input submission
        Posted when user presses Enter
        """
        # Post our custom UserSubmitted message
        self.post_message(self.UserSubmitted(event.value, self))