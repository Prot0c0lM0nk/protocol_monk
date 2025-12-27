"""
ui/textual/widgets/chat_display.py
Handles mixed-mode display: Markdown for chat, Static/Markup for tools.
"""

from textual.containers import VerticalScroll
from textual.widgets import Markdown, Static
from textual.message import Message


class ChatMessage(Markdown):
    """A message bubble rendered as Markdown (for User/Agent text)."""

    pass


class ToolResultWidget(Static):
    """A result block rendered with Rich Markup (for colors)."""

    pass


class ChatDisplay(VerticalScroll):
    """
    A scrolling container that stacks Markdown messages and Tool Results.
    """

    def __init__(self):
        super().__init__()
        self.current_stream_text = ""
        self.active_agent_message: ChatMessage = None

    def compose(self):
        yield Static(classes="spacer")

    def add_user_message(self, text: str):
        """Add a finished user message to the scroll."""
        msg = ChatMessage(f"**USER:** {text}", classes="user-msg")
        self.mount(msg)
        self.scroll_end(animate=False)

    def write_to_log(self, text: str):
        """
        Append chunk to the active agent message (Markdown).
        """
        if self.active_agent_message is None:
            self.current_stream_text = ""
            self.active_agent_message = ChatMessage("", classes="agent-msg")
            self.mount(self.active_agent_message)

        self.current_stream_text += text

        # Render as Markdown
        display_text = f"**AGENT:**\n\n{self.current_stream_text}"
        self.active_agent_message.update(display_text)
        self.scroll_end(animate=False)

    def add_tool_output(self, tool_name: str, output: str, success: bool):
        """
        Add a tool result block (Static with Markup).
        Call this instead of write_to_log for tool results.
        """
        # Close any active stream first
        self.end_current_message()

        color = "green" if success else "red"
        # We use Rich markup here ([bold], [color])
        markup_text = f"[bold {color}]Tool: {tool_name}[/]\n{output}"

        result_widget = ToolResultWidget(
            markup_text, markup=True, classes="tool-output"
        )
        self.mount(result_widget)
        self.scroll_end(animate=False)

    def end_current_message(self):
        """Close the active stream."""
        self.active_agent_message = None
        self.current_stream_text = ""
