"""Tool confirmation modal for sensitive tool executions."""

from rich.syntax import Syntax
from rich.text import Text

from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Grid, Vertical, VerticalScroll
from textual.widgets import Button, Label, Static
from textual.binding import Binding


class ToolConfirmModal(ModalScreen[str]):
    """
    A modal dialog that asks the user to confirm a tool execution.
    Returns one of: "approved", "approved_auto", "rejected".
    """

    CSS = """
    ToolConfirmModal {
        align: center middle;
        background: #03070d 80%;
    }

    #dialog {
        background: #111923;
        border: thick #00b8d9;
        width: 90%;
        height: 85%;
        padding: 1 2;
    }

    #question {
        text-style: bold;
        margin-bottom: 1;
        color: #d5e6f8;
    }

    #summary {
        color: #8fa6bd;
        margin-bottom: 1;
    }

    #preview-scroll {
        height: 1fr;
        border: solid #f8c96c;
        background: #0a1017;
        margin-bottom: 1;
        padding: 1;
    }

    #preview-content {
        background: #0a1017;
        color: #d5e6f8;
        height: auto;
    }

    #buttons {
        layout: grid;
        grid-size: 3;
        grid-gutter: 2;
        width: 100%;
        height: auto;
        align: center bottom;
    }

    Button {
        width: 100%;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("escape", "deny", "Deny"),
        Binding("enter", "approve", "Approve"),
        Binding("y", "approve", "Approve"),
        Binding("a", "approve_auto", "Approve + Auto"),
        Binding("n", "deny", "Deny"),
    ]

    def __init__(self, tool_name: str, parameters: dict):
        super().__init__()
        self.tool_name = str(tool_name or "Unknown Tool")
        self.tool_args = parameters or {}
        self.preview_summary = f"Tool: {self.tool_name}"
        self.preview_text = self._build_preview_text()

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Allow Tool Execution?", id="question")
            yield Label(self.preview_summary, id="summary")
            with VerticalScroll(id="preview-scroll"):
                yield Static(self._render_preview(), id="preview-content")

            with Grid(id="buttons"):
                yield Button("Deny (Esc)", variant="error", id="deny")
                yield Button("Allow (Enter)", variant="success", id="approve")
                yield Button("Allow + Auto (A)", variant="primary", id="approve_auto")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "approve":
            self.dismiss("approved")
            return
        if event.button.id == "approve_auto":
            self.dismiss("approved_auto")
            return
        self.dismiss("rejected")

    def action_approve(self) -> None:
        self.dismiss("approved")

    def action_approve_auto(self) -> None:
        self.dismiss("approved_auto")

    def action_deny(self) -> None:
        self.dismiss("rejected")

    def _build_preview_text(self) -> str:
        return "\n".join(
            [
                f"Tool: {self.tool_name}",
                "",
                "Arguments:",
                *[f"  {k}: {v}" for k, v in self.tool_args.items()],
            ]
        )

    def _render_preview(self):
        text = self.preview_text
        if "\n" in text and any(key in text for key in ("{", "}", "[", "]")):
            return Syntax(text, "python", word_wrap=True, line_numbers=False)
        return Text(text)
