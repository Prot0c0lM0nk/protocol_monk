"""
ui/textual/app.py
The Protocol Monk Textual Application - Worker Edition
Refactored for Event Bubbling and Modal Waiting.
"""

import asyncio
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, Input
from textual.screen import Screen

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

    CSS_PATH = ["styles/main.tcss", "styles/components.tcss", "styles/chat.tcss"]

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("ctrl+p", "command_palette", "Commands"),
        Binding("f1", "show_help", "Help"),
    ]

    COMMANDS = {AgentCommandProvider}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.textual_ui = None
        self.agent = None  # Injected by main.py
        self._input_future = None  # The bridge for user input

    def compose(self) -> ComposeResult:
        """Create the app layout."""
        yield Header()
        yield MainChatScreen()
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the app and START THE AGENT WORKER."""
        self.notify("Protocol Monk TUI Ready", severity="information")
        self.push_screen(MainChatScreen())

        if self.agent:
            # Launch the agent in a dedicated worker thread/task
            # group="agent" allows us to manage it collectively
            self.run_worker(
                self._agent_runner(), name="agent_brain", group="agent", exclusive=True
            )
        else:
            self.notify("⚠️ No Agent Connected!", severity="error")

    async def _agent_runner(self):
        """The dedicated coroutine for the Agent Worker."""
        try:
            await self.agent.run()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.notify(f"Agent Crashed: {e}", severity="error")

    # --- 1. CRITICAL FIX: MODAL WAITER ---
    async def push_screen_wait(self, screen: Screen) -> Any:
        """
        A custom wrapper to await a screen's result linearly.
        Used by interface.py for Tool Confirmations.
        """
        wait_future = asyncio.Future()

        def callback(result: Any):
            wait_future.set_result(result)

        self.push_screen(screen, callback=callback)
        return await wait_future

    # --- 2. CRITICAL FIX: INPUT HAND-OFF ---
    async def get_user_input_wait(self) -> str:
        """
        Wait for user input.
        The Agent Worker calls this and sleeps here until input arrives.
        """
        self._input_future = asyncio.Future()
        try:
            # Block the Agent Worker until the UI thread resolves this future
            return await self._input_future
        finally:
            self._input_future = None

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """
        Handle input from ANY Input widget (including our InputBar).
        This runs on the UI thread.
        """
        user_text = event.value

        # 1. Show the user's message immediately (Optimistic UI)
        if hasattr(self.screen, "add_user_message"):
            asyncio.create_task(self.screen.add_user_message(user_text))

        # 2. If the Agent is waiting for input, give it to them
        if self._input_future and not self._input_future.done():
            self._input_future.set_result(user_text)

        # 3. If Agent is NOT waiting (e.g., busy thinking), notify user
        else:
            # Optional: You could queue this, but for now we warn
            self.notify("Agent is busy processing...", severity="warning")

    # --- Message Handlers (The UI Thread) ---
    # These handle events coming FROM the Agent (via interface.py)

    def on_agent_stream_chunk(self, message: AgentStreamChunk) -> None:
        if hasattr(self.screen, "add_stream_chunk"):
            self.screen.add_stream_chunk(message.chunk)

    def on_agent_thinking_status(self, message: AgentThinkingStatus) -> None:
        if hasattr(self.screen, "show_thinking"):
            self.screen.show_thinking(message.is_thinking)

    def on_agent_tool_result(self, message: AgentToolResult) -> None:
        if hasattr(self.screen, "add_tool_result"):
            self.screen.add_tool_result(message.tool_name, message.result)

    def on_agent_status_update(self, message: AgentStatusUpdate) -> None:
        if hasattr(self.screen, "update_status_bar"):
            self.screen.update_status_bar(message.stats)
        else:
            try:
                # Fallback search for the widget
                status_bar = self.query_one("StatusBar")
                status_bar.update_metrics(message.stats)
            except Exception:
                pass

    def on_agent_system_message(self, message: AgentSystemMessage) -> None:
        if message.type == "error":
            self.notify(message.message, severity="error")
        elif message.type == "info":
            self.notify(message.message, severity="information")
        elif message.type == "response_complete":
            if hasattr(self.screen, "finalize_response"):
                self.screen.finalize_response()
