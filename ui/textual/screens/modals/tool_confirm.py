"""
ui/textual/screens/modals/tool_confirm.py
Modal screen for confirming tool execution.
"""

from pathlib import Path

from rich.syntax import Syntax
from rich.text import Text

from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Grid, Vertical, VerticalScroll
from textual.widgets import Button, Label, Static
from textual.binding import Binding

from ...tool_preview import build_tool_preview

class ToolConfirmModal(ModalScreen[bool]):
    """
    A modal dialog that asks the user to confirm a tool execution.
    Returns True if confirmed, False if denied.
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
        grid-size: 2;
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
        working_dir = tool_data.get("working_dir")
        if isinstance(working_dir, Path):
            self.working_dir = str(working_dir)
        else:
            self.working_dir = str(working_dir) if working_dir else None

        preview = build_tool_preview(self.tool_name, self.tool_args, self.working_dir)
        self.preview_summary = preview.summary
        self.preview_text = preview.full_text
        self.preview_syntax = preview.syntax_hint

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("Allow Tool Execution?", id="question")
            yield Label(self.preview_summary, id="summary")
            with VerticalScroll(id="preview-scroll"):
                yield Static(self._render_preview(), id="preview-content")

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

    def _render_preview(self):
        syntax_hint = (self.preview_syntax or "").lower()
        lexer = None
        if syntax_hint in {"diff", "patch"}:
            lexer = "diff"
        elif syntax_hint in {"python", "py"}:
            lexer = "python"
        elif syntax_hint in {"bash", "shell", "sh"}:
            lexer = "bash"
        elif syntax_hint in {"json"}:
            lexer = "json"

        if lexer:
            return Syntax(self.preview_text, lexer, word_wrap=True, line_numbers=False)
        return Text(self.preview_text)
