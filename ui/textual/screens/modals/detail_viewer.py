"""
ui/textual/screens/modals/detail_viewer.py
Modal for displaying full tool/thinking detail content.
"""

from rich.syntax import Syntax
from rich.text import Text

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from ...models import DetailRecord


class DetailViewerModal(ModalScreen[None]):
    """Displays full detail text in a scrollable popup."""

    CSS = """
    DetailViewerModal {
        align: center middle;
        background: $background 80%;
    }

    #detail-dialog {
        width: 90%;
        height: 85%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    #detail-title {
        text-style: bold;
        margin-bottom: 1;
    }

    #detail-summary {
        color: #9aa3ad;
        margin-bottom: 1;
    }

    #detail-scroll {
        height: 1fr;
        border: solid $accent;
        background: $background;
        margin-bottom: 1;
        padding: 1;
    }

    #detail-buttons {
        align: right middle;
        height: auto;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter", "close", "Close"),
    ]

    def __init__(self, record: DetailRecord):
        super().__init__()
        self.record = record

    def compose(self) -> ComposeResult:
        with Vertical(id="detail-dialog"):
            yield Label(self.record.title, id="detail-title")
            if self.record.summary:
                yield Label(self.record.summary, id="detail-summary")
            with VerticalScroll(id="detail-scroll"):
                yield Static(self._render_content(), id="detail-content")
            with Horizontal(id="detail-buttons"):
                yield Button("Close (Esc)", id="close", variant="primary")

    def _render_content(self):
        """Return a Rich renderable for the detail body."""
        text = self.record.full_text or "(no detail content)"
        syntax_hint = (self.record.syntax_hint or "").lower()

        lexer = None
        if syntax_hint in {"diff", "patch"}:
            lexer = "diff"
        elif syntax_hint in {"python", "py"}:
            lexer = "python"
        elif syntax_hint in {"bash", "sh", "shell"}:
            lexer = "bash"
        elif syntax_hint in {"json"}:
            lexer = "json"

        if lexer:
            return Syntax(text, lexer, word_wrap=True, line_numbers=False)
        return Text(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.dismiss(None)

    def action_close(self) -> None:
        self.dismiss(None)
