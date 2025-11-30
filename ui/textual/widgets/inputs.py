from textual.events import Key
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, TextArea


class InputPanel(Widget):
    """Handle user input via text area and send button."""

    class Submit(Message):
        """Event sent when user submits input."""

        def __init__(self, text: str):
            super().__init__()
            self.text = text

    def __init__(self):
        super().__init__()
        self.mount(
            TextArea(id="input", placeholder="Type your message..."),
            Button("Send", variant="primary", id="send"),
        )

    def on_mount(self):
        """Initialize components after mounting."""
        self._textarea = self.query_one("#input")
        self._button = self.query_one("#send")

    def on_button_pressed(self, event: Button.Pressed):
        """Handle button press event."""
        if event.button.id == "send":
            text = self._textarea.text
            if text.strip():
                self.post_message(self.Submit(text))
                self._textarea.clear()

    def on_key(self, event: Key):
        """Handle key press events (Enter without Shift)."""
        if event.key == "enter" and not event.shift:
            text = self._textarea.text
            if text.strip():
                self.post_message(self.Submit(text))
                self._textarea.clear()
                event.prevent_default()
