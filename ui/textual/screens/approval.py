"""
Tool approval modal for Protocol Monk's Textual UI.
"""

from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, Button, Pretty, Static
from textual.containers import Container, Horizontal
from typing import Dict, Any


class ApprovalScreen(ModalScreen[bool]):
    """Modal screen for tool call approval.

    Attributes:
        DEFAULT_CSS (str): The default CSS styling for the approval screen.
    """

    DEFAULT_CSS = """
    ApprovalScreen {
        align: center middle;
        background: $bg-black 80%;
        border: double $holy-gold;
        width: 80;
        height: auto;
    }
    #approval_container {
        width: 100%;
        height: auto;
        padding: 1;
    }
    #tool_name {
        text-style: bold;
        color: $holy-gold;
        content-align: center top;
    }
    #params_display {
        width: 100%;
        height: auto;
        border: solid $monk-text;
        padding: 1;
    }
    #button_container {
        width: 100%;
        height: auto;
        align: center middle;
        padding: 1;
    }
    Button {
        width: 12;
        margin: 1;
    }
    Button.-success {
        color: $monk-text;
        background: $holy-gold;
    }
    Button.-error {
        color: $monk-text;
        background: #ff0000;
    }
    """

    def __init__(self, tool_call: Dict[str, Any], *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.tool_call = tool_call

    def compose(self) -> ComposeResult:
        """Compose the approval screen layout."""
        with Container(id="approval_container"):
            yield Label(
                f"Tool Request: {self.tool_call.get('tool_name', 'Unknown')}",
                id="tool_name",
            )
            yield Pretty(self.tool_call.get("parameters", {}), id="params_display")
            with Horizontal(id="button_container"):
                yield Button("Authorize", variant="success", id="authorize")
                yield Button("Deny", variant="error", id="deny")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses for authorization."""
        if event.button.id == "authorize":
            self.dismiss(True)
        else:
            self.dismiss(False)
