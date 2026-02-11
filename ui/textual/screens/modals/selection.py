"""
ui/textual/screens/modals/selection.py
Modal screen for selecting an item from a list.
"""

from typing import List, Optional

from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Vertical, Grid
from textual.widgets import Button, Label, ListView, ListItem
from textual.binding import Binding


class SelectionModal(ModalScreen[Optional[int]]):
    """
    A modal dialog that lets the user select an item from a list.
    Returns the selected index (0-based) or None if canceled.
    """

    CSS = """
    SelectionModal {
        align: center middle;
        background: #03070d 80%;
    }

    #dialog {
        background: #111923;
        border: thick #00b8d9;
        width: 80%;
        height: 70%;
        padding: 1 2;
    }

    #title {
        text-style: bold;
        margin-bottom: 1;
        color: #d5e6f8;
    }

    #list {
        height: 1fr;
        border: solid #f8c96c;
        background: #0a1017;
        margin-bottom: 1;
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
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    def __init__(self, title: str, options: List[str]):
        super().__init__()
        self.title = title
        self.options = options
        self.selected_index: Optional[int] = 0 if options else None

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self.title, id="title")
            with ListView(id="list"):
                for opt in self.options:
                    yield ListItem(Label(opt))
            with Grid(id="buttons"):
                yield Button("Cancel (Esc)", variant="error", id="cancel")
                yield Button("Select (Enter)", variant="success", id="confirm")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        # Update selection on click/enter but do not dismiss here
        self.selected_index = event.index

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self.action_confirm()
        else:
            self.action_cancel()

    def action_confirm(self) -> None:
        try:
            list_view = self.query_one(ListView)
            if list_view.index is not None:
                self.selected_index = list_view.index
        except Exception:
            pass
        self.dismiss(self.selected_index)

    def action_cancel(self) -> None:
        self.dismiss(None)
