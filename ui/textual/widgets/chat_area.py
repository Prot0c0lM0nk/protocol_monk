# ui/textual/widgets/chat_area.py

from textual.app import ComposeResult
from textual.containers import VerticalScroll, Container
from textual.widgets import Static

class UserMessageBubble(Static):
    """The visual bubble for user input."""
    
    def on_mount(self) -> None:
        # Check content length for auto-collapse logic if desired
        if len(str(self.renderable)) > 500:
            self.add_class("collapsed")

class AIResponseCanvas(Static):
    """The full-width Markdown canvas for AI responses."""
    pass

class ChatArea(VerticalScroll):
    """The main chat container."""

    def compose(self) -> ComposeResult:
        # Start with a welcome message or empty
        yield AIResponseCanvas(
            "# Protocol Monk\n\n"
            "I am ready to serve. My responses will render here as full Markdown."
        )

    async def add_user_message(self, content: str) -> None:
        """Mounts a user bubble, wrapped in a right-aligned container."""
        bubble = UserMessageBubble(content)
        
        # Wrapper to force right alignment
        row = Container(classes="user-message-row")
        row.mount(bubble)
        
        await self.mount(row)
        row.scroll_visible()

    async def add_ai_message(self, content: str) -> None:
        """Mounts the AI canvas directly to the scroll area."""
        canvas = AIResponseCanvas(content)
        await self.mount(canvas)
        canvas.scroll_visible()