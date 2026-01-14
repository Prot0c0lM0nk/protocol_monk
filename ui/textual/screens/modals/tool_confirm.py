"""
ui/textual/screens/modals/tool_confirm.py
Modal screen for confirming tool execution.
"""

from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Grid, Vertical
from textual.widgets import Button, Label, Static
from textual.binding import Binding


class ToolConfirmModal(ModalScreen[bool]):
    """
    A modal dialog that asks the user to confirm a tool execution.
    Returns True if confirmed, False if denied.
    """

    CSS = """
    ToolConfirmModal {
        align: center middle;
        background: $background 80%; /* Semi-transparent dimming */
    }

    #dialog {
        background: $surface;
        border: thick $primary;
        width: 60;
        height: auto;
        padding: 2;
    }

    #question {
        text-align: center;
        width: 100%;
        margin-bottom: 1;
        text-style: bold;
    }

    #tool-details {
        background: $background;
        border: solid $accent;
        padding: 1;
        margin-bottom: 2;
        color: $text;
        height: auto;
        max-height: 20;
    }

    #buttons {
        layout: grid;
        grid-size: 2;
        grid-gutter: 2;
        width: 100%;
        height: auto;
        align: center bottom;
    }

    Button {
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "deny", "Deny"),
        Binding("enter", "confirm", "Confirm"),
    ]

    def __init__(self, tool_data: dict):
        """
        Args:
            tool_data: Dictionary containing 'tool' (name) and 'args' (arguments)
        """
        super().__init__()
        self.tool_name = tool_data.get("tool", "Unknown Tool")
        self.tool_args = tool_data.get("args", {})
        
        # Format arguments for display
        self.args_str = "\n".join(f"{k}: {v}" for k, v in self.tool_args.items())

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("⚠️ Allow Tool Execution?", id="question")
            
            # Display tool details
            details = f"Tool: {self.tool_name}\n\nArguments:\n{self.args_str}"
            yield Static(details, id="tool-details")
            
            with Grid(id="buttons"):
                yield Button("Deny (Esc)", variant="error", id="deny")
                yield Button("Allow (Enter)", variant="success", id="confirm")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_deny(self) -> None:
        self.dismiss(False)