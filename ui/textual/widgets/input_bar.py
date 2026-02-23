"""Input bar aligned to reference container structure."""

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Input, TextArea


class InputBar(Horizontal):
    def compose(self) -> ComposeResult:
        text_area = TextArea(id="msg-input", show_line_numbers=False)
        text_area.placeholder = "Ask Protocol Monk..."
        yield text_area
        yield Button("Send", id="send-btn", variant="primary")

    def on_mount(self) -> None:
        self.focus_input()

    def focus_input(self) -> None:
        self.query_one("#msg-input", TextArea).focus()

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            # Don't steal Enter from modals or other focused controls.
            focused = getattr(self.app, "focused", None)
            if focused is None or getattr(focused, "id", None) != "msg-input":
                return
            event.stop()
            event.prevent_default()
            self._submit_message()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "send-btn":
            self._submit_message()

    def _submit_message(self) -> None:
        input_widget = self.query_one("#msg-input", TextArea)
        value = input_widget.text.strip()
        if not value:
            return
        self.post_message(Input.Submitted(input_widget, value))
        input_widget.text = ""
