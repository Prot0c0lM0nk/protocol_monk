# ui/textual/widgets/input_bar.py

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import TextArea, Button
from textual import events

class InputBar(Horizontal):
    """
    A multi-line input bar.
    Enter -> Send
    Shift+Enter -> New Line (handled natively by TextArea)
    """

    def compose(self) -> ComposeResult:
        # We use TextArea for multiline support
        text_area = TextArea(id="msg-input", show_line_numbers=False)
        text_area.placeholder = "Ask Protocol Monk..."
        yield text_area
        
        yield Button("Send", id="send-btn", variant="primary")

    def on_mount(self) -> None:
        """Focus the input automatically."""
        self.query_one("#msg-input").focus()

    def on_key(self, event: events.Key) -> None:
        """
        Intercept Enter to submit. 
        Shift+Enter comes through as a distinct key 'shift+enter', so we ignore it here
        and let the TextArea handle it (creating a new line).
        """
        if event.key == "enter":
            # Stop the newline from happening and submit
            event.stop()
            event.prevent_default()
            self._submit_message()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            self._submit_message()

    def _submit_message(self) -> None:
        text_widget = self.query_one("#msg-input", TextArea)
        value = text_widget.text.strip()
        
        if value:
            self.app.call_from_child_submit(value)
            text_widget.text = ""