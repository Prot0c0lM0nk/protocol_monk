"""
ui/textual/widgets/chat_input.py
"""
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import TextArea, Button
from textual.message import Message
from textual.binding import Binding

class ChatInput(Container):
    """
    A composite widget containing a multi-line text area and a send button.
    Behaves like a proper editor: Enter = New Line.
    """

    # Add a specific binding for submitting via keyboard if desired
    BINDINGS = [
        Binding("ctrl+enter", "submit", "Send Message", show=False),
    ]

    class Submitted(Message):
        """Event sent when the message is finalized."""
        def __init__(self, value: str):
            self.value = value
            super().__init__()

    def compose(self):
        # We use a Horizontal container to put the text area and button side-by-side
        # or Vertical if you prefer the button below. Let's try side-by-side first.
        with Horizontal(id="input_container"):
            yield TextArea(id="message_input", show_line_numbers=False)
            yield Button("SEND", id="send_button", variant="success")

    def on_mount(self):
        """Configure the text area on startup."""
        text_area = self.query_one(TextArea)
        text_area.focus()

    async def action_submit(self):
        """Triggered by Ctrl+Enter or the Button."""
        text_area = self.query_one(TextArea)
        value = text_area.text.strip()
        
        if value:
            # 1. Clear the input
            text_area.text = ""
            # 2. Post the message up to the parent
            self.post_message(self.Submitted(value))

    def on_button_pressed(self, event: Button.Pressed):
        """Handle the UI button click."""
        if event.button.id == "send_button":
            self.action_submit()