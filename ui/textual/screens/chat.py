"""
The main chat screen for Protocol Monk's Textual UI.
"""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer
from textual.containers import VerticalScroll
from textual.message import Message

from ui.textual.widgets.inputs import MatrixInput
from ui.textual.widgets.messages import ChatBubble


class ChatScreen(Screen):
    """The main chat interface screen.

    Attributes:
        DEFAULT_CSS (str): The default CSS styling for the chat screen.
    """

    DEFAULT_CSS = """
    ChatScreen {
        align: center top;
    }
    #chat_scroll {
        height: 100%;
        width: 100%;
        scrollbar-gutter: stable;
    }
    """

    class InputSubmitted(Message):
        """Posted when the input is submitted from this screen.

        Attributes:
            value (str): The submitted input value.
        """

        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(self, initial_prompt: str = "", *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.initial_prompt = initial_prompt

    def compose(self) -> ComposeResult:
        """Compose the chat screen layout."""
        yield Header()
        yield VerticalScroll(id="chat_scroll")
        yield MatrixInput(id="user_input", placeholder="Type your prayer...")

    def on_mount(self) -> None:
        """Initialize the screen after mounting."""
        if self.initial_prompt:
            self.action_add_bubble(self.initial_prompt, "system")
        self.query_one(MatrixInput).focus()

    def action_add_bubble(self, text: str, sender: str = "user") -> None:
        """Add a new chat bubble to the scroll area.

        Args:
            text (str): The text content of the bubble.
            sender (str): The sender type ('user', 'monk', or 'system').
        """
        chat_scroll = self.query_one(VerticalScroll)
        chat_scroll.mount(ChatBubble(text, sender))
        chat_scroll.scroll_end(animate=False)

    def update_stream(self, text: str) -> None:
        """Update the last chat bubble with streaming text.

        Args:
            text (str): The new text to append to the last bubble.
        """
        chat_scroll = self.query_one(VerticalScroll)
        if bubbles := chat_scroll.query(ChatBubble):
            bubbles.last().update_text(text)
            chat_scroll.scroll_end(animate=False)

    def on_matrix_input_submitted(self, message: MatrixInput.InputSubmitted) -> None:
        """Handle input submission from the MatrixInput."""
        self.action_add_bubble(message.value, "user")
        self.post_message(self.InputSubmitted(message.value))
