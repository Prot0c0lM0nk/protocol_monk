"""
ui/textual/widgets/chat_area.py
Chat area widget for Protocol Monk TUI
"""

import asyncio

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Markdown, Static
from textual import events


class UserMessage(Markdown):
    """User message bubble (Grey)."""
    pass


class AIMessage(Markdown):
    """AI message bubble (Monk Green)."""
    pass


class ThinkingIndicator(Static):
    """Thinking indicator widget."""
    pass


class ToolResultWidget(Static):
    """Tool result display widget."""
    pass


class ChatArea(VerticalScroll):
    """Main chat area that displays conversation history."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._current_ai_message = None
        self._thinking_indicator = None

    def compose(self) -> ComposeResult:
        """Create the initial chat area content."""
        # Start with empty chat area - no initial greeting
        # Messages will be added as they come in
        # Return empty generator to satisfy Textual's compose requirement
        if False:
            yield  # This will never execute but satisfies the return type

    async def add_user_message(self, content: str) -> None:
        """Add a user message to the chat."""
        msg = UserMessage(content)
        await self.mount(msg)
        msg.scroll_visible()

    async def add_ai_message(self, content: str) -> None:
        """Add a new AI message to the chat."""
        # Finalize any previous AI message first
        self.finalize_response()
        
        # Create new AI message
        self._current_ai_message = AIMessage(content)
        await self.mount(self._current_ai_message)
        self._current_ai_message.scroll_visible()

    def add_stream_chunk(self, chunk: str) -> None:
        """Add a streaming chunk to the current AI message."""
        if self._current_ai_message is None:
            # Start a new AI message if none exists
            self._current_ai_message = AIMessage(chunk)
            self.call_later(self.mount, self._current_ai_message)
        else:
            # Append to existing message
            current_content = self._current_ai_message.document.text
            new_content = current_content + chunk
            self._current_ai_message.update(new_content)
        
        # Scroll to make the new content visible
        if self._current_ai_message:
            self._current_ai_message.scroll_visible()

    def show_thinking(self, is_thinking: bool) -> None:
        """Show or hide the thinking indicator."""
        if is_thinking:
            if self._thinking_indicator is None:
                self._thinking_indicator = ThinkingIndicator("🤔 Thinking...")
                self.call_later(self.mount, self._thinking_indicator)
        else:
            if self._thinking_indicator is not None:
                self._thinking_indicator.remove()
                self._thinking_indicator = None

    def add_tool_result(self, tool_name: str, result) -> None:
        """Add a tool result to the chat."""
        success_icon = "✅" if result.success else "❌"
        tool_widget = ToolResultWidget(
            f"{success_icon} **{tool_name}**: {result.output}"
        )
        self.call_later(self.mount, tool_widget)

    def finalize_response(self) -> None:
        """Finalize the current AI response."""
        # Hide thinking indicator
        self.show_thinking(False)
        
        # Reset current AI message pointer
        self._current_ai_message = None