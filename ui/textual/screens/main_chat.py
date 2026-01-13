"""
ui/textual/screens/main_chat.py
Main chat screen for Protocol Monk TUI
"""

import asyncio
from textual.screen import Screen
from textual.widgets import Header, Footer
from ..widgets.chat_area import ChatArea
from ..widgets.input_bar import InputBar


class MainChatScreen(Screen):
    """Main chat interface screen."""

    def compose(self):
        """Create the screen layout."""
        yield Header()
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

    def add_stream_chunk(self, chunk: str) -> None:
        """Add a streaming chunk to the current AI message."""
        chat_area = self.query_one(ChatArea)
        chat_area.add_stream_chunk(chunk)

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

    async def await_user_input(self, prompt: str = "") -> str:
        """
        Wait for user input from the input bar.
        This is called by the agent when it needs user input.
        """
        input_bar = self.query_one(InputBar)
        
        # Set a placeholder if prompt is provided
        if prompt:
            text_area = input_bar.query_one("#msg-input")
            if text_area:
                text_area.placeholder = prompt
        
        # Focus the input
        input_bar.focus_input()
        
        # Create a future to wait for input
        future = asyncio.Future()
        
        # Store the future in the input bar so it can resolve it
        input_bar.set_input_future(future)
        
        try:
            result = await future
            return result
        finally:
            # Reset placeholder
            if prompt and text_area:
                text_area.placeholder = "Ask Protocol Monk..."