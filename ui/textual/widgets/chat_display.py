"""
ui/textual/widgets/chat_display.py
Widget for displaying chat messages
"""

from textual.widgets import RichLog
from textual.message import Message
from typing import Optional


class ChatDisplay(RichLog):
    """
    Chat display widget
    Shows conversation history with the agent
    """

    class Submitted(Message):
        """Message posted when user submits input (for bubbling)"""
        def __init__(self, value: str, input_widget: "ChatInput") -> None:
            self.value = value
            self.input_widget = input_widget
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.auto_scroll = True
        self.wrap = True

    def add_message(self, sender: str, content: str, style: str = "") -> None:
        """
        Add a message to the chat display

        Args:
            sender: Message sender ("user", "agent", "system", "error")
            content: Message content
            style: Optional style string
        """
        # Format message based on sender
        if sender == "user":
            prefix = "[bold cyan]You:[/bold cyan] "
        elif sender == "agent":
            prefix = "[bold green]Monk:[/bold green] "
        elif sender == "system":
            prefix = "[bold yellow]System:[/bold yellow] "
        elif sender == "error":
            prefix = "[bold red]Error:[/bold red] "
        else:
            prefix = f"[bold]{sender}:[/bold] "

        # Add message to log
        self.write(f"{prefix}{content}")

    def clear_messages(self) -> None:
        """Clear all messages from the chat display"""
        self.clear()

    def add_thinking(self, message: str = "Thinking...") -> None:
        """
        Add a thinking indicator

        Args:
            message: Thinking message text
        """
        self.write(f"[dim italic]{message}[/dim italic]")

    def add_tool_result(self, tool_name: str, result: str, success: bool = True) -> None:
        """
        Add a tool execution result

        Args:
            tool_name: Name of the tool
            result: Tool output
            success: Whether the tool succeeded
        """
        if success:
            prefix = f"[bold green]✓ {tool_name}:[/bold green] "
        else:
            prefix = f"[bold red]✗ {tool_name}:[/bold red] "
        self.write(f"{prefix}{result}")