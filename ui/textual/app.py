"""
ui/textual/app.py
The Protocol Monk Textual Application - Worker Edition
"""

import asyncio
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

from .command_provider import AgentCommandProvider

from .screens.main_chat import MainChatScreen
from .interface import TextualUI
from .messages import (
    AgentStreamChunk,
    AgentThinkingStatus,
    AgentToolResult,
    AgentSystemMessage,
    AgentStatusUpdate,
)

class ProtocolMonkApp(App):
    """Protocol Monk - The Oracle of the Holy Light"""

    CSS_PATH = [
        "styles/main.tcss",
        "styles/components.tcss",
        "styles/chat.tcss"
    ]

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("ctrl+p", "command_palette", "Commands"),
        Binding("f1", "show_help", "Help"),
    ]

    COMMANDS = {AgentCommandProvider}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.textual_ui = None
        self.agent = None          # Injected by main.py
        self._input_future = None  # The bridge for user input

    def compose(self) -> ComposeResult:
        """Create the app layout."""
        yield Header()
        yield MainChatScreen()
        yield Footer()

    def on_mount(self) -> None:
        """
        Initialize the app and START THE AGENT WORKER.
        The App owns the Agent's lifecycle.
        """
        self.notify("Protocol Monk TUI Ready", severity="information")
        self.push_screen(MainChatScreen())

        if self.agent:
            # === THE WORKER SOCKET ===
            # We launch the agent immediately. Textual manages this task.
            # If the App closes, Textual cancels this worker automatically[cite: 72].
            self.run_worker(self._agent_runner(), name="agent_brain", group="agent", exclusive=True)
        else:
            self.notify("⚠️ No Agent Connected!", severity="error")

    async def _agent_runner(self):
        """The dedicated coroutine for the Agent Worker."""
        try:
            # This will run forever until the App exits
            await self.agent.run()
        except asyncio.CancelledError:
            # Normal shutdown behavior [cite: 65]
            pass 
        except Exception as e:
            self.notify(f"Agent Crashed: {e}", severity="error")

    async def get_user_input_wait(self) -> str:
        """
        Wait for user input. 
        The Agent Worker calls this and sleeps here until input arrives.
        """
        self._input_future = asyncio.Future()

        # Connect the future to the InputBar widget
        screen = self.screen
        if hasattr(screen, 'query_one'):
            try:
                screen.query_one("InputBar").set_input_future(self._input_future)
            except Exception:
                pass

        try:
            # Block the Agent Worker (not the UI thread) until input is ready
            return await self._input_future
        finally:
            self._input_future = None

    # --- Message Handlers (The UI Thread) ---
    
    def on_agent_stream_chunk(self, message: AgentStreamChunk) -> None:
        """Handle streaming text."""
        if hasattr(self.screen, 'add_stream_chunk'):
            self.screen.add_stream_chunk(message.chunk)

    def on_agent_thinking_status(self, message: AgentThinkingStatus) -> None:
        """Handle thinking status."""
        if hasattr(self.screen, 'show_thinking'):
            self.screen.show_thinking(message.is_thinking)

    def on_agent_tool_result(self, message: AgentToolResult) -> None:
        """Handle tool results."""
        if hasattr(self.screen, 'add_tool_result'):
            self.screen.add_tool_result(message.tool_name, message.result)

    def on_agent_status_update(self, message: AgentStatusUpdate) -> None:
        """Handle status updates from the agent."""
        if hasattr(self.screen, 'update_status_bar'):
            self.screen.update_status_bar(message.stats)
        # Fallback: Try querying the widget directly if screen helper missing
        else:
            try:
                status_bar = self.screen.query_one("StatusBar")
                if status_bar:
                    status_bar.update_metrics(message.stats)
            except Exception:
                pass

    def on_agent_system_message(self, message: AgentSystemMessage) -> None:
        """Handle system messages."""
        if message.type == "error":
            self.notify(message.message, severity="error")
        elif message.type == "info":
            self.notify(message.message, severity="information")
        elif message.type == "response_complete":
            if hasattr(self.screen, 'finalize_response'):
                self.screen.finalize_response()