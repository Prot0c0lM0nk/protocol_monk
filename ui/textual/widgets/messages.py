"""
Chat bubble widgets for the Protocol Monk Textual UI.
"""

from textual.widgets import Static
from textual.containers import Horizontal
from rich.markdown import Markdown


class ChatBubble(Static):
    """A chat bubble widget that renders text with sender-specific styling.

    Attributes:
        text (str): The content to display in the bubble.
        sender (str): The sender type ('user', 'monk', or 'system').
    """

    DEFAULT_CSS = """
    ChatBubble {
        width: auto;
        max-width: 80%;
        padding: 1;
        margin: 1 2;
        border: solid $monk-text;
        border-title-align: left;
    }
    ChatBubble.-user {
        border-title-color: $holy-gold;
        border-title-style: bold;
        text-style: italic;
    }
    ChatBubble.-monk {
        border-title-color: $tech-cyan;
        border-title-style: bold;
    }
    ChatBubble.-system {
        border-title-color: $tech-cyan;
        border-title-style: dim;
    }
    """

    def __init__(self, text: str, sender: str = "monk", *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.text = text
        self.sender = sender.lower()
        self.add_class(f"-{self.sender}")
        self.border_title = sender.capitalize()

    def on_mount(self) -> None:
        """Render the initial content when mounted."""
        self.update_text(self.text)

    def update_text(self, content: str) -> None:
        """Update the bubble's content (for streaming).

        Args:
            content (str): The new text to display.
        """
        self.update(Markdown(content))

    def compose(self) -> None:
        """Compose the bubble's content."""
        yield Horizontal(Markdown(self.text), classes=f"bubble-{self.sender}")
