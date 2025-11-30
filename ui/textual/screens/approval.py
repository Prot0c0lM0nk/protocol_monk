from textual import on
from textual.screen import ModalScreen
from textual.widgets import Button, Label
from typing import Any


class ApprovalScreen(ModalScreen):
    """Modal for approving/denying tool calls."""

    def __init__(self, tool_call: Any):
        super().__init__()
        self.tool_call = tool_call

    def on_mount(self):
        """Initialize components after mounting."""
        # Display tool name and arguments
        tool_name = self.tool_call.get("name", "Unknown Tool")
        tool_args = self.tool_call.get("args", "No args")
        self.mount(
            Label(f"Tool: {tool_name}\nArgs: {tool_args}"),
            Button("Approve", id="approve", variant="success"),
            Button("Deny", id="deny", variant="error"),
        )

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed):
        """Handle button press events."""
        if event.button.id == "approve":
            self.dismiss(True)
        elif event.button.id == "deny":
            self.dismiss(False)
