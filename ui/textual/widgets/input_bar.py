"""
ui/textual/widgets/input_bar.py
Multi-line input bar for Protocol Monk TUI
"""

import asyncio
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._input_future = None

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

    def set_input_future(self, future: asyncio.Future) -> None:
        """Set the future to resolve when input is received."""
        self._input_future = future

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
        """Handle button press events."""
        if event.button.id == "send-btn":
            self._submit_message()

    def _submit_message(self) -> None:
        """Submit the current message."""
        text_widget = self.query_one("#msg-input", TextArea)
        value = text_widget.text.strip()

        if value:
            # Check if we're waiting for input from the agent
            if self._input_future and not self._input_future.done():
                # Agent is waiting - just resolve the future, don't submit to app
                self._input_future.set_result(value)
                self._input_future = None
                text_widget.text = ""
            else:
                # Normal user submission - send to app
                self.app.call_from_child_submit(value)
                text_widget.text = ""