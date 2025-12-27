"""
ui/textual/screens/selection.py
Generic modal for selecting an item from a list.
"""
from textual.screen import ModalScreen
from textual.app import ComposeResult
from textual.containers import Vertical, Grid
from textual.widgets import Button, Label, OptionList

class SelectionModal(ModalScreen[str]):
    """
    A modal that presents a list of options and returns the selected string.
    """

    def __init__(self, title: str, options: list[str]):
        super().__init__()
        self.selection_title = title
        self.options = options

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_dialog"):
            yield Label(self.selection_title, id="title")
            
            # The list of choices
            yield OptionList(*self.options, id="selection_list")
            
            # Buttons
            with Grid(id="button_grid", classes="selection_buttons"):
                yield Button("Select", variant="success", id="btn_select")
                yield Button("Cancel", variant="error", id="btn_cancel")

    def on_mount(self):
        # Focus the list so arrow keys work immediately
        self.query_one("#selection_list").focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected):
        """Handle Enter/Click on a list item."""
        self.dismiss(str(event.option.prompt))

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "btn_select":
            # Get current highlighted item
            opt_list = self.query_one(OptionList)
            if opt_list.highlighted is not None:
                selected_idx = opt_list.highlighted
                # Retrieve the text from the option at that index
                # Textual < 0.38 might differ, but generally:
                label = str(opt_list.get_option_at_index(selected_idx).prompt)
                self.dismiss(label)
        
        elif event.button.id == "btn_cancel":
            self.dismiss(None)