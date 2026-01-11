"""
ui/textual/widgets/chat_display.py
Widget for displaying chat messages as bubbles
"""

from textual.containers import VerticalScroll
from textual.widgets import Static
from textual.message import Message
# 1. Fixed Import
from .chat_input import ChatInput

class ChatMessage(Static):
    """Individual message bubble widget"""
    def __init__(self, content: str, sender: str, **kwargs):
        super().__init__(content, **kwargs)
        self.sender = sender
        self.add_class(f"message-{sender}")
        self.add_class("message")

class ChatDisplay(VerticalScroll):
    """
    Chat display widget
    Shows conversation history as a list of scrollable message bubbles
    """

    class Submitted(Message):
        """Message posted when user submits input"""
        def __init__(self, value: str, input_widget: "ChatInput") -> None:
            self.value = value
            self.input_widget = input_widget
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.auto_scroll = True

    def add_message(self, sender: str, content: str, style: str = "") -> None:
        """Add a message bubble to the chat display"""
        # Create widget
        message_widget = ChatMessage(content, sender=sender)
        
        # Add to scroll view
        self.mount(message_widget)
        
        # 2. Fixed Method: VerticalScroll uses scroll_end(), not scroll_to_end()
        self.scroll_end(animate=False)

    def add_thinking(self, message: str = "Thinking...") -> None:
        """Add a thinking indicator"""
        self.add_message("system", f"[dim italic]{message}[/dim italic]")

    def add_tool_result(self, tool_name: str, result: str, success: bool = True) -> None:
        """Add a tool execution result"""
        status = "✓" if success else "✗"
        content = f"[bold]{status} {tool_name}:[/bold]\n{result}"
        self.add_message("tool", content)

    def clear_messages(self) -> None:
        """Clear all messages"""
        self.remove_children()