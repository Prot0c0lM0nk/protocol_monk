"""
ui/textual/app.py
The Receiver: Handles EventBus messages and manages the Widget Tree.
"""

import asyncio
from pathlib import Path
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static
from textual.binding import Binding

# Import screens
from .screens.chat_screen import ChatScreen
from .screens.tool_confirm import ToolConfirmModal

# Import NEW Message Protocol
from .messages import (
    AgentStreamChunk,
    AgentThinkingStatus,
    AgentToolResult,
    AgentSystemMessage,
)

# Import Provider
from .commands import MonkCommandProvider


class ProtocolMonkApp(App):
    """
    The Protocol Monk TUI.
    Now acts as a Reactive View driven by Agent Messages.
    """

    # Fix CSS Path to be absolute or relative safe
    CSS_PATH = "styles/orthodox.tcss"
    TITLE = "Protocol Monk ✠"

    # Register Command Palette Provider
    COMMANDS = {MonkCommandProvider}

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_screen", "Clear"),
    ]

    def __init__(self):
        super().__init__()
        self.input_future: asyncio.Future = None
        self.input_handler = None  # Function to call when user hits enter

    # --- 1. CORE LIFECYCLE ---

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield ChatScreen(id="chat_screen")
        yield Footer()

    def on_mount(self) -> None:
        self.notify("Protocol Monk Initialized", title="System")

    def set_input_handler(self, handler):
        """Register the async function to call with user input."""
        self.input_handler = handler

    # --- 2. THE FIX: BLOCKING MODALS ---

    async def push_screen_wait(self, screen_instance):
        """
        Push a screen and wait asynchronously for its result.
        Crucial for Tool Confirmation flows.
        """
        future = asyncio.Future()

        def callback(result):
            if not future.done():
                future.set_result(result)

        # Hijack the on_dismiss callback to capture the result
        screen_instance.on_dismiss = callback

        self.push_screen(screen_instance)
        return await future

    async def get_user_input_wait(self) -> str:
        """
        Called by Interface when Agent specifically requests input via get_input().
        We focus the chat box and wait for the next submission.
        """
        screen = self.query_one(ChatScreen)
        screen.focus_input()

        # Create a future that resolve_input will complete
        self.input_future = asyncio.Future()
        return await self.input_future

    # --- 3. INPUT HANDLING ---

    def resolve_input(self, value: str):
        """Called by ChatInput widget when user presses Enter."""

        # Scenario A: Agent is waiting for specific input (via get_input)
        if self.input_future and not self.input_future.done():
            self.input_future.set_result(value)
            self.input_future = None
            return

        # Scenario B: Standard Chat Loop
        if self.input_handler:
            # Run the agent interaction in the background
            self.run_worker(self.input_handler(value))

    def action_clear_screen(self):
        """Binding: Ctrl+L"""
        try:
            screen = self.query_one(ChatScreen)
            display = screen.query_one("ChatDisplay")
            # We assume ChatDisplay has a clear method or we clear children
            if hasattr(display, "clear"):
                display.clear()
            else:
                # Fallback: remove all children if it's a generic container
                display.remove_children()
                display.mount(Static(classes="spacer"))
            self.notify("Screen Cleared")
        except Exception:
            pass

    def trigger_slash_command(self, command: str):
        """Command Palette hook."""
        if self.input_handler:
            self.run_worker(self.input_handler(command))

    # --- 4. MESSAGE HANDLERS (The Bridge Receivers) ---

    def on_agent_stream_chunk(self, message: AgentStreamChunk):
        """Handle real-time text."""
        self.query_one(ChatScreen).write_to_log(message.chunk)

    def on_agent_thinking_status(self, message: AgentThinkingStatus):
        """Show/Hide spinner."""
        screen = self.query_one(ChatScreen)
        if message.is_thinking:
            if hasattr(screen, "show_loading_indicator"):
                screen.show_loading_indicator()
        else:
            if hasattr(screen, "finalize_response"):
                screen.finalize_response()

    def on_agent_tool_result(self, message: AgentToolResult):
        """Render a tool result panel."""
        screen = self.query_one(ChatScreen)
        display = screen.query_one("ChatDisplay")

        # Use the specific widget method to add the formatted result
        display.add_tool_output(
            tool_name=message.tool_name,
            output=message.result.output,
            success=message.result.success,
        )

    def on_agent_system_message(self, message: AgentSystemMessage):
        """Handle system events."""
        if message.type == "error":
            self.notify(message.text, severity="error")
            # Optionally log to chat as well
            self.query_one(ChatScreen).write_system_message(f"ERROR: {message.text}")

        elif message.type == "info":
            self.notify(message.text, severity="information")

        elif message.type == "response_complete":
            # Ensure any dangling state is closed
            screen = self.query_one(ChatScreen)
            if hasattr(screen, "finalize_response"):
                screen.finalize_response()
