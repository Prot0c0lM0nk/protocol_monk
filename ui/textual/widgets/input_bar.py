"""
ui/textual/widgets/input_bar.py
Multi-line input bar for Protocol Monk TUI.
Now decoupled: It simply fires an event when input is ready.
"""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import TextArea, Button, Input
from textual import events


class InputBar(Horizontal):
    """
    A multi-line input bar.
    Enter -> Send (Emits Input.Submitted)
    Shift+Enter -> New Line
    """

    def compose(self) -> ComposeResult:
        """Create the input bar layout."""
        # We use TextArea for multiline support
        text_area = TextArea(id="msg-input", show_line_numbers=False)
        text_area.placeholder = "Ask Protocol Monk..."
        yield text_area

        yield Button("Send", id="send-btn", variant="primary")

    def on_mount(self) -> None:
        """Focus the input automatically."""
        self.focus_input()

    def focus_input(self) -> None:
        """Focus the text input area."""
        text_area = self.query_one("#msg-input", TextArea)
        text_area.focus()

    def on_key(self, event: events.Key) -> None:
        """
        Intercept Enter to submit.
        Shift+Enter is handled natively by TextArea (new line).
        """
        if event.key == "enter":
            # Stop the newline from happening and submit
            event.stop()
            event.prevent_default()
            self._submit_message()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "send-btn":
            self._submit_message()

    def _submit_message(self) -> None:
        """
        Get text, clear input, and fire the event up the DOM.
        """
        text_widget = self.query_one("#msg-input", TextArea)
        value = text_widget.text.strip()

        if value:
            # We manually create an Input.Submitted event.
            # This allows the App to handle it exactly like a standard Input widget.
            # We pass 'text_widget' as the sender so the App knows where it came from.
            self.post_message(Input.Submitted(text_widget, value))

            # Clear the box
            text_widget.text = ""
