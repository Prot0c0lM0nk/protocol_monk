from textual.app import ComposeResult
from textual.screen import ModalScreen
from textual.widgets import Label, Button, Static
from textual.containers import Grid, Container
from rich.json import JSON


class ToolConfirmationScreen(ModalScreen[bool]):
    """
    Modal dialog for tool approval.
    Returns True if approved, False if rejected.
    """

    CSS_PATH = "../styles.tcss"  # Ensure this path is correct relative to file

    def __init__(self, tool_data: dict):
        super().__init__()
        self.tool_data = tool_data

    def compose(self) -> ComposeResult:
        tool_name = self.tool_data.get("tool_name", "Unknown Tool")
        params = self.tool_data.get("parameters", {})

        yield Container(
            Label("⚠️ Tool Execution Request", id="confirmation-title"),
            Label(f"The agent wants to execute: [b]{tool_name}[/b]"),
            Static(JSON.from_data(params), classes="code-block"),
            Container(
                Button("Approve", variant="success", id="approve-btn"),
                Button("Reject", variant="error", id="reject-btn"),
                id="confirmation-buttons",
            ),
            id="confirmation-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "approve-btn":
            self.dismiss(True)
        else:
            self.dismiss(False)
