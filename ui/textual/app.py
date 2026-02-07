"""
ui/textual/app.py
The Protocol Monk Textual Application - Worker Edition
Refactored for Event Bubbling and Modal Waiting.
"""

import asyncio
import os
from typing import Any, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Input
from textual.screen import Screen

from .command_provider import AgentCommandProvider
from agent.events import AgentEvents

from .screens.main_chat import MainChatScreen
from .screens.startup import CinematicStartupScreen
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
        "styles/chat.tcss",
        "styles/startup.tcss",
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
        self.agent = None  # Injected by main.py
        self.agent_ready_task: Optional[asyncio.Task] = None  # Injected by main.py
        self.event_bus = None  # Injected by main.py
        self._input_future = None  # The bridge for user input
        self._main_screen_shown = False

    def compose(self) -> ComposeResult:
        """The app uses pushed screens for full control of startup flow."""
        if False:
            yield

    def on_mount(self) -> None:
        """Initialize startup flow: cinematic intro first, then main chat."""
        asyncio.create_task(self._launch_startup_flow())

    async def _launch_startup_flow(self) -> None:
        """Play startup intro unless disabled, then enter main chat."""
        self.notify("Protocol Monk TUI Ready", severity="information")

        skip_intro = os.getenv("PROTOCOL_MONK_SKIP_STARTUP", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if not skip_intro:
            try:
                await self.push_screen_wait(
                    CinematicStartupScreen(ready_task=self.agent_ready_task)
                )
            except Exception:
                pass

        await self._wait_for_agent_ready()

        if not self.agent:
            self.notify("⚠️ No Agent Connected!", severity="error")
        self._enter_main_chat()

    async def _wait_for_agent_ready(self) -> None:
        """Ensure the agent service is initialized before entering chat."""
        if not self.agent_ready_task:
            return
        try:
            await self.agent_ready_task
        except Exception as error:
            self.notify(f"⚠️ Agent init failed: {error}", severity="error")

    def _enter_main_chat(self) -> None:
        """Switch to the main chat screen exactly once."""
        if self._main_screen_shown:
            return
        self._main_screen_shown = True
        self.push_screen(MainChatScreen())

        # Kick a first status refresh so the bar isn't empty at startup
        if self.textual_ui and hasattr(self.textual_ui, "_refresh_status"):
            asyncio.create_task(self.textual_ui._refresh_status())

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
        stripped_text = user_text.strip()

        # In Textual, /status is a UI command that refreshes the status bar.
        if (
            stripped_text.lower() == "/status"
            and not (self._input_future and not self._input_future.done())
        ):
            if self.textual_ui and hasattr(self.textual_ui, "_refresh_status"):
                asyncio.create_task(self.textual_ui._refresh_status())
                self.notify("Status bar refreshed", severity="information")
            else:
                self.notify("Status bar unavailable", severity="warning")
            return

        # 1. Show the user's message immediately (Optimistic UI)
        if hasattr(self.screen, "add_user_message"):
            asyncio.create_task(self.screen.add_user_message(user_text))

        # 2. If the Agent is waiting for input, give it to them
        if self._input_future and not self._input_future.done():
            self._input_future.set_result(user_text)

        # 3. If Agent is NOT waiting, emit USER_INPUT to the event bus
        elif self.event_bus:
            asyncio.create_task(
                self.event_bus.emit(AgentEvents.USER_INPUT.value, {"input": user_text})
            )

        # 4. If Agent is NOT waiting and no event bus, notify user
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
        try:
            status_bar = self.query_one("StatusBar")
            status_bar.status = "Thinking" if message.is_thinking else "Ready"
        except Exception:
            pass

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
