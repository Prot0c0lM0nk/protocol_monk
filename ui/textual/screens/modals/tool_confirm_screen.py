"""
ui/textual/screens/modals/tool_confirm_screen.py
Modal dialog for confirming tool execution
"""
from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button, Label
from typing import Dict, Any


class ToolConfirmScreen(ModalScreen[bool]):
    """
    Modal screen for tool execution confirmation
    Returns True if approved, False if rejected
    """

    BINDINGS = [
        ("y", "approve", "Approve"),
        ("n", "reject", "Reject"),
        ("escape", "reject", "Cancel"),
    ]

    def __init__(self, tool_name: str, parameters: Dict[str, Any]) -> None:
        super().__init__()
        self.tool_name = tool_name
        self.parameters = parameters

    def compose(self) -> ComposeResult:
        """Compose the tool confirmation dialog"""
        with Vertical(id="dialog"):
            yield Static(f"Execute Tool: {self.tool_name}", id="title")
            yield Static(f"Parameters: {self.parameters}", id="params")
            with Horizontal(id="buttons"):
                yield Button("Approve (Y)", variant="success", id="approve")
                yield Button("Reject (N)", variant="error", id="reject")

    def action_approve(self) -> None:
        """Approve tool execution"""
        self.dismiss(True)

    def action_reject(self) -> None:
        """Reject tool execution"""
        self.dismiss(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "approve":
            self.action_approve()
        elif event.button.id == "reject":
            self.action_reject()