from textual.widgets import Static
from textual.containers import VerticalScroll
from rich.markdown import Markdown


class AgentMessage(Static):
    """
    Displays response from the Agent. Supports streaming updates.
    """

    DEFAULT_CSS = """
    /* Theme variables - using hex values directly */
    AgentMessage {
        padding: 1 2;
        margin-bottom: 1;
        background: #10B981 15%; /* $secondary-color 15% */
        border-left: wide #10B981; /* $secondary-color */
        dock: left;
        width: 85%;
        height: auto;
    }
    """

    def __init__(self, content: str = "", **kwargs):
        super().__init__(Markdown(content), classes="agent-message", **kwargs)
        self._content = content

    def update_chunk(self, chunk: str) -> None:
        """Appends text to the message and re-renders Markdown."""
        self._content += chunk
        self.update(Markdown(self._content))


class UserMessage(Static):
    """
    Displays input from the User.
    """

    DEFAULT_CSS = """
    UserMessage {
        padding: 1 2;
        margin-bottom: 1;
        background: #3B82F6 15%; /* $primary-color 15% */
        border-left: wide #3B82F6; /* $primary-color */
        dock: right;
        text-align: right;
        width: 85%;
        height: auto;
    }
    """

    def __init__(self, content: str, **kwargs):
        # We render user text as plain string or simple markup, not full MD usually
        super().__init__(content, classes="user-message", **kwargs)


class ToolResultMessage(Static):
    """
    Displays the result of a tool execution (e.g., file content, command output).
    """

    DEFAULT_CSS = """
    ToolResultMessage {
        background: #1E293B; /* $surface-color */
        border: solid #94A3B8; /* $dim-text */
        padding: 1;
        margin: 1 4;
        width: 90%;
        height: auto;
        max-height: 20; /* Limit height to prevent huge logs taking over */
        overflow-y: auto;
    }
    """

    def __init__(self, tool_name: str, output: str, **kwargs):
        display_text = f"🔧 **Tool: {tool_name}**\n\n```\n{output}\n```"
        super().__init__(Markdown(display_text), classes="tool-result", **kwargs)


class ChatArea(VerticalScroll):
    """
    Main container for the chat history.
    """

    DEFAULT_CSS = """
    ChatArea {
        width: 100%;
        height: 1fr;
        padding: 1;
    }
    """

    def on_mount(self):
        self.can_focus = False  # Keep focus in input bar
