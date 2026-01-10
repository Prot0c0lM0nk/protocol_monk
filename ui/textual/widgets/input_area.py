from textual.widgets import Input
from textual.containers import Container


class UserInput(Container):
    """
    Container for the input field.
    """

    DEFAULT_CSS = """
    /* GLOBAL THEME VARIABLES - Copied for widget styling */
    UserInput {
        dock: bottom;
        height: 3;
        padding: 0;
        background: #0F172A; /* $bg-color equivalent */
    }
    
    Input {
        width: 100%;
        background: #1E293B; /* $surface-color equivalent */
        border: solid #3B82F6; /* $primary-color equivalent */
        color: #F8FAFC; /* $text-color equivalent */
    }
    
    Input:focus {
        border: double #3B82F6; /* $primary-color equivalent */
    }
    """

    def compose(self):
        yield Input(placeholder="Type your instruction here...", id="input-box")

    @property
    def value(self) -> str:
        return self.query_one(Input).value

    @value.setter
    def value(self, text: str) -> None:
        self.query_one(Input).value = text
