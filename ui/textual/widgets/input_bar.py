# ui/textual/widgets/input_bar.py

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Input, Button

class InputBar(Horizontal):
    """Fixed bottom input area."""

    def compose(self) -> ComposeResult:
        # The + Button (Command Palette trigger)
        yield Button("+", id="cmd-btn", variant="primary")
        
        # The main input
        yield Input(placeholder="Ask Protocol Monk...", id="msg-input")
        
        # The Send Button (optional icon or text)
        yield Button("➤", id="send-btn", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cmd-btn":
            self.app.action_command_palette()
        elif event.button.id == "send-btn":
            self._submit_message()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._submit_message()

    def _submit_message(self) -> None:
        input_widget = self.query_one("#msg-input", Input)
        value = input_widget.value.strip()
        
        if value:
            # We will wire this up to the App logic next
            self.app.call_from_child_submit(value)
            input_widget.value = ""