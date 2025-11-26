from textual.widget import Widget
from textual.widgets import Markdown
from typing import Literal


class ChatMessage(Widget):
    """Display individual chat messages."""
    def __init__(self, role: Literal["user", "assistant", "tool"], content: str):
        super().__init__()
        self.role = role
        self.content = content
        self._update_render()

    def _update_render(self):
        """Render the message based on role."""
        if self.role == "user":
            self.add_class("user")
            self.update(self.content)
        elif self.role == "assistant":
            self.add_class("assistant")
            self.content_widget = Markdown(self.content)
            self.update(self.content_widget)
        elif self.role == "tool":
            self.add_class("tool")
            self.update(self.content)
        else:
            self.update(self.content)

    def append_text(self, text: str):
        """Update message content (if Markdown widget exists)."""
        self.content += text
        if hasattr(self, 'content_widget') and isinstance(self.content_widget, Markdown):
            self.content_widget.update(self.content)
        else:
            self.update(self.content)