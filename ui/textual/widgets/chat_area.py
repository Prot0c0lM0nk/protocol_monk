# ui/textual/widgets/chat_area.py

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Markdown

class UserMessage(Markdown):
    """User message bubble (Grey)."""
    pass

class AIMessage(Markdown):
    """AI message bubble (Monk Green)."""
    pass

class ChatArea(VerticalScroll):
    def compose(self) -> ComposeResult:
        # Initial greeting rendered as proper Markdown
        yield AIMessage(
            "# Protocol Monk\n"
            "I am ready to serve. My responses will render here as **full Markdown**."
        )

    async def add_user_message(self, content: str) -> None:
        # Create and mount
        msg = UserMessage(content)
        await self.mount(msg)
        msg.scroll_visible()

    async def add_ai_message(self, content: str) -> None:
        msg = AIMessage(content)
        await self.mount(msg)
        msg.scroll_visible()