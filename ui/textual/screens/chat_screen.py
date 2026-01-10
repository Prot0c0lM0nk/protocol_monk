from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer, Input
from textual import on

from ui.textual.widgets import (
    ChatArea,
    UserInput,
    AgentMessage,
    UserMessage,
    ToolResultMessage,
    MonkHeader,
)
from ui.textual.messages import (
    StreamChunkMsg,
    ToolResultMsg,
    AgentLogMsg,
    StatusUpdateMsg,
)


class ChatScreen(Screen):
    """
    The primary interface for the Protocol Monk agent.
    """

    def compose(self) -> ComposeResult:
        yield MonkHeader()
        yield ChatArea(id="chat-area")
        yield UserInput(id="user-input")
        yield Footer()

    def on_mount(self) -> None:
        """Focus input on start."""
        self.query_one("#input-box").focus()

    @on(Input.Submitted)
    def on_input_submitted(self, event) -> None:
        """Handle user hitting Enter in the input box."""
        input_widget = self.query_one("#input-box")
        text = input_widget.value.strip()

        if text:
            # 1. Clear Input
            input_widget.value = ""

            # 2. Display User Message locally
            self.query_one("#chat-area").mount(UserMessage(text))

            # 3. Send to Agent (via App's controller)
            self.app.handle_user_input(text)

            # 4. Create a placeholder AgentMessage for the response
            # We mount it now so stream chunks have a target
            self.current_agent_message = AgentMessage("")
            self.query_one("#chat-area").mount(self.current_agent_message)

            # 5. Scroll to bottom
            self.query_one("#chat-area").scroll_end(animate=True)

    @on(StreamChunkMsg)
    def on_stream_chunk(self, message: StreamChunkMsg) -> None:
        """Receive a stream chunk from the agent."""
        if hasattr(self, "current_agent_message"):
            self.current_agent_message.update_chunk(message.chunk)
            self.query_one("#chat-area").scroll_end(animate=False)

    @on(ToolResultMsg)
    def on_tool_result(self, message: ToolResultMsg) -> None:
        """Display the result of a tool execution."""
        # Mount the result message
        result_widget = ToolResultMessage(message.tool_name, str(message.result))
        self.query_one("#chat-area").mount(result_widget)

        # Prepare a NEW AgentMessage for any subsequent text (like "I have finished...")
        self.current_agent_message = AgentMessage("")
        self.query_one("#chat-area").mount(self.current_agent_message)

        self.query_one("#chat-area").scroll_end(animate=True)

    @on(AgentLogMsg)
    def on_agent_log(self, message: AgentLogMsg) -> None:
        """Handle system notifications."""
        if message.level == "error":
            self.notify(message.message, severity="error")
        elif message.level == "warning":
            self.notify(message.message, severity="warning")
        else:
            self.notify(message.message, severity="information")
