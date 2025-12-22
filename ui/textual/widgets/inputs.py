"""
Custom input widgets for the Protocol Monk Textual UI.
"""

from textual.widgets import Input
from textual.message import Message


class MatrixInput(Input):
    """A custom input bar with Matrix styling and enhanced behavior.

    Attributes:
        DEFAULT_CSS (str): The default CSS styling for the input bar.
    """

    DEFAULT_CSS = """
    MatrixInput {
        dock: bottom;
        width: 100%;
        height: 3;
        color: #00FF00;  /* Matrix Green - $monk-text */
        border: solid #00FF00;  /* Matrix Green - $monk-text */
        background: #050505 50%;  /* $bg-black */
    }
    MatrixInput > .input--cursor {
        color: #ffaa44;  /* Orthodox Gold - $holy-gold */
        background: #00FF00;  /* Matrix Green - $monk-text */
    }
    """

    class InputSubmitted(Message):
        """Posted when the input is submitted.

        Attributes:
            value (str): The submitted input value.
        """

        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def on_key(self, event) -> None:
        """Handle key presses to submit input.

        Args:
            event: The key event to handle.
        """
        if event.key == "enter" and self.value:
            self.post_message(self.InputSubmitted(self.value))
            self.value = ""  # Clear input after submission
