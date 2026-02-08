"""
ui/textual/screens/main_chat.py
Main chat screen for Protocol Monk TUI
"""

import logging
from typing import Optional
from textual.screen import Screen
from textual.widgets import Footer
from ..widgets.chat_area import ChatArea
from ..widgets.input_bar import InputBar
from ..widgets.status_bar import StatusBar


logger = logging.getLogger(__name__)


class MainChatScreen(Screen):
    """Main chat interface screen."""

    def compose(self):
        """Create the screen layout."""
        yield StatusBar(id="status-bar")
        yield ChatArea()
        yield InputBar()
        yield Footer()

    async def add_user_message(self, content: str) -> None:
        """Add a user message to the chat area."""
        chat_area = self.query_one(ChatArea)
        await chat_area.add_user_message(content)

    async def add_ai_message(self, content: str) -> None:
        """Add an AI message to the chat area."""
        chat_area = self.query_one(ChatArea)
        await chat_area.add_ai_message(content)

    def add_stream_chunk(self, chunk: str, is_thinking: bool = False) -> None:
        """Add a streaming chunk to the current AI message."""
        chat_area = self.query_one(ChatArea)
        chat_area.add_stream_chunk(chunk, is_thinking=is_thinking)

    def show_thinking(self, is_thinking: bool) -> None:
        """Show or hide the thinking indicator."""
        chat_area = self.query_one(ChatArea)
        chat_area.show_thinking(is_thinking)

    def add_tool_result(self, tool_name: str, result) -> None:
        """Add a tool result to the chat area."""
        chat_area = self.query_one(ChatArea)
        chat_area.add_tool_result(tool_name, result)

    def finalize_response(self) -> None:
        """Finalize the current AI response."""
        chat_area = self.query_one(ChatArea)
        chat_area.finalize_response()

    def open_detail(self, detail_id: Optional[str] = None) -> None:
        """Open detail modal for the given detail record ID."""
        chat_area = self.query_one(ChatArea)
        chat_area.open_detail(detail_id)

    def last_detail_id(self) -> Optional[str]:
        """Return the latest detail record ID in the current session."""
        chat_area = self.query_one(ChatArea)
        return chat_area.last_detail_id()

    def update_status_bar(self, stats: dict) -> None:
        """Update the status bar with new stats."""
        try:
            status_bar = self.query_one("#status-bar", StatusBar)
            status_bar.update_metrics(stats)
        except Exception as error:
            logger.exception("Status bar update failed.")
            self.app.notify(
                f"Status bar update failed: {error}",
                severity="error",
            )
