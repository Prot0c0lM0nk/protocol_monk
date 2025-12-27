"""
ui/textual/widgets/chat_display.py
"""
from textual.containers import VerticalScroll
from textual.widgets import Markdown, Static
from textual.message import Message

class ChatMessage(Markdown):
    """A single message bubble in the chat."""
    pass

class ChatDisplay(VerticalScroll):
    """
    A scrolling container that stacks Markdown messages.
    """
    
    def __init__(self):
        super().__init__()
        # Buffer to hold the text of the message currently being streamed
        self.current_stream_text = ""
        # Reference to the active widget being updated
        self.active_agent_message: ChatMessage = None

    def compose(self):
        # Start with a spacer or welcome message if desired
        yield Static(classes="spacer")

    def add_user_message(self, text: str):
        """Add a finished user message to the scroll."""
        # Create a new message widget with user styling
        msg = ChatMessage(f"**USER:** {text}", classes="user-msg")
        self.mount(msg)
        self.scroll_end(animate=False)

    def write_to_log(self, text: str):
        """
        Append chunk to the active agent message.
        If no message is active, create one.
        """
        # If this is the start of a new response
        if self.active_agent_message is None:
            self.current_stream_text = ""
            self.active_agent_message = ChatMessage("", classes="agent-msg")
            self.mount(self.active_agent_message)

        # Append text to buffer
        self.current_stream_text += text
        
        # Update the markdown content (Agent label + content)
        # We add the label manually since we are rendering raw markdown
        display_text = f"**AGENT:**\n\n{self.current_stream_text}"
        self.active_agent_message.update(display_text)
        
        # Keep scrolling to bottom
        self.scroll_end(animate=False)

    def end_current_message(self):
        """Called when streaming stops to 'seal' the message."""
        self.active_agent_message = None
        self.current_stream_text = ""