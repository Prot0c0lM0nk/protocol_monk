"""
ui/textual/widgets/chat_display.py
Widget for displaying chat messages as bubbles
"""

from textual.containers import VerticalScroll, Horizontal
from textual.widgets import Static
from textual.message import Message
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
        def __init__(self, value: str, input_widget: "ChatInput") -> None:
            self.value = value
            self.input_widget = input_widget
            super().__init__()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.auto_scroll = True
        self.current_response_text = ""
        self.current_response_widget = None # The text bubble itself
        self.thinking_row = None           # The container holding the thinking bubble

    def add_message(self, sender: str, content: str, style: str = "") -> None:
        """Add a message bubble to the chat display"""
        
        # 1. Clear "Thinking..." if it exists
        if self.thinking_row:
            self.thinking_row.remove()
            self.thinking_row = None

        # 2. Agent Streaming Logic
        if sender == "agent":
            if self.current_response_widget is not None:
                # Append to existing bubble
                self.current_response_text += content
                self.current_response_widget.update(self.current_response_text)
            else:
                # Start new stream
                self.current_response_text = content
                self.current_response_widget = ChatMessage(content, sender=sender)
                
                # Wrap in a ROW container for alignment
                row = Horizontal(self.current_response_widget, classes="message-row row-left")
                self.mount(row)

        # 3. User / System Logic (Always new row)
        else:
            # Reset agent stream if user interrupts
            self.current_response_widget = None
            self.current_response_text = ""
            
            message_widget = ChatMessage(content, sender=sender)
            
            # Determine alignment
            align_class = "row-right" if sender == "user" else "row-left"
            
            # Wrap in Row
            row = Horizontal(message_widget, classes=f"message-row {align_class}")
            self.mount(row)
        
        self.scroll_end(animate=False)

    def write(self, text: str) -> None:
        """Shim for app.py to signal end of stream/thinking"""
        if text == "":
            self.current_response_widget = None
            self.current_response_text = ""
            # If thinking is still up, remove it
            if self.thinking_row:
                self.thinking_row.remove()
                self.thinking_row = None

    def add_thinking(self, message: str = "Thinking...") -> None:
        """Add a thinking indicator"""
        if self.thinking_row:
            self.thinking_row.remove()
            
        # Create thinking bubble
        thinking_widget = ChatMessage(f"[dim italic]{message}[/dim italic]", sender="system")
        
        # Wrap in Row (Left Aligned)
        self.thinking_row = Horizontal(thinking_widget, classes="message-row row-left")
        self.mount(self.thinking_row)
        self.scroll_end(animate=False)

    def add_tool_result(self, tool_name: str, result: str, success: bool = True) -> None:
        status = "✓" if success else "✗"
        content = f"[bold]{status} {tool_name}:[/bold]\n{result}"
        self.add_message("tool", content)

    def clear_messages(self) -> None:
        self.remove_children()
        self.current_response_widget = None
        self.thinking_row = None