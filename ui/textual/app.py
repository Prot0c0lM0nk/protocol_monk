"""
ui/textual/app.py
Main Textual App for Protocol Monk
"""

import asyncio
from typing import Dict, Any

from textual.app import App, ComposeResult
from textual.message import Message
from textual import work

from .screens.chat_screen import ChatScreen
from .screens.settings_screen import SettingsScreen
from .screens.help_screen import HelpScreen
from .screens.modals.tool_confirm_screen import ToolConfirmScreen
from .screens.modals.quit_confirm_screen import QuitConfirmScreen
from agent.events import get_event_bus, AgentEvents


class TextualUI(App):
    """
    Main Textual App for Protocol Monk
    ChatGPT-like terminal agent interface
    """

    CSS_PATH = "styles/main.tcss"

    # Screen modes
    MODES = {
        "chat": ChatScreen,
        "settings": SettingsScreen,
        "help": HelpScreen,
    }
    DEFAULT_MODE = "chat"

    # Modal screens
    SCREENS = {
        "tool_confirm": ToolConfirmScreen,
        "quit_confirm": QuitConfirmScreen,
    }

    # Key bindings
    BINDINGS = [
        ("ctrl+c", "request_quit", "Quit"),
        ("ctrl+s", "switch_mode('settings')", "Settings"),
        ("ctrl+h", "switch_mode('help')", "Help"),
        ("escape", "switch_mode('chat')", "Chat"),
    ]

    # Custom message for agent events
    class AgentEvent(Message):
        """Message posted when agent emits an event"""
        def __init__(self, event_type: str, data: Dict[str, Any]) -> None:
            self.event_type = event_type
            self.data = data
            super().__init__()

    def __init__(self):
        super().__init__()
        self._event_bus = get_event_bus()
        self._input_future: asyncio.Future = None
        self._tool_confirm_future: asyncio.Future = None
        self._setup_event_listeners()

    def _setup_event_listeners(self):
        """Subscribe to agent event bus"""
        # Subscribe to all agent events
        self._event_bus.subscribe(AgentEvents.STREAM_CHUNK.value, self._on_stream_chunk)
        self._event_bus.subscribe(AgentEvents.RESPONSE_COMPLETE.value, self._on_response_complete)
        self._event_bus.subscribe(AgentEvents.TOOL_RESULT.value, self._on_tool_result)
        self._event_bus.subscribe(AgentEvents.ERROR.value, self._on_agent_error)
        self._event_bus.subscribe(AgentEvents.WARNING.value, self._on_agent_warning)
        self._event_bus.subscribe(AgentEvents.INFO.value, self._on_agent_info)
        self._event_bus.subscribe(AgentEvents.THINKING_STARTED.value, self._on_thinking_started)
        self._event_bus.subscribe(AgentEvents.THINKING_STOPPED.value, self._on_thinking_stopped)
        self._event_bus.subscribe(AgentEvents.TOOL_CONFIRMATION_REQUESTED.value, self._on_tool_confirmation_requested)

    def on_mount(self) -> None:
        """Called when app is mounted"""
        self.switch_mode("chat")

    def action_request_quit(self) -> None:
        """Show quit confirmation dialog"""
        self.push_screen("quit_confirm")

    # --- BLOCKING METHODS (Called by Agent) ---

    async def get_input(self) -> str:
        """
        Get user input from chat input widget
        BLOCKS until user submits input
        """
        self._input_future = asyncio.Future()

        # Focus the input widget
        try:
            chat_screen = self.screen_stack[0]
            input_widget = chat_screen.query_one("#user-input")
            input_widget.focus()
        except:
            pass

        # Wait for user to submit
        return await self._input_future

    async def confirm_tool_execution(self, tool_data: Dict[str, Any]) -> bool:
        """
        Ask user to confirm tool execution
        BLOCKS until user approves or rejects
        """
        tool_name = tool_data.get("tool_name", "Unknown")
        parameters = tool_data.get("parameters", {})

        # Show confirmation modal
        result = await self.push_screen_wait(ToolConfirmScreen(tool_name, parameters))
        return result

    # --- EVENT HANDLERS (Called by Agent Event Bus) ---

    async def _on_stream_chunk(self, data: Dict[str, Any]):
        """Handle stream chunk event"""
        # Post to message queue for UI thread
        self.post_message(self.AgentEvent(AgentEvents.STREAM_CHUNK.value, data))

    async def _on_response_complete(self, data: Dict[str, Any]):
        """Handle response complete event"""
        self.post_message(self.AgentEvent(AgentEvents.RESPONSE_COMPLETE.value, data))

    async def _on_tool_result(self, data: Dict[str, Any]):
        """Handle tool result event"""
        self.post_message(self.AgentEvent(AgentEvents.TOOL_RESULT.value, data))

    async def _on_agent_error(self, data: Dict[str, Any]):
        """Handle agent error event"""
        self.post_message(self.AgentEvent(AgentEvents.ERROR.value, data))

    async def _on_agent_warning(self, data: Dict[str, Any]):
        """Handle agent warning event"""
        self.post_message(self.AgentEvent(AgentEvents.WARNING.value, data))

    async def _on_agent_info(self, data: Dict[str, Any]):
        """Handle agent info event"""
        self.post_message(self.AgentEvent(AgentEvents.INFO.value, data))

    async def _on_thinking_started(self, data: Dict[str, Any]):
        """Handle thinking started event"""
        self.post_message(self.AgentEvent(AgentEvents.THINKING_STARTED.value, data))

    async def _on_thinking_stopped(self, data: Dict[str, Any]):
        """Handle thinking stopped event"""
        self.post_message(self.AgentEvent(AgentEvents.THINKING_STOPPED.value, data))

    async def _on_tool_confirmation_requested(self, data: Dict[str, Any]):
        """Handle tool confirmation requested event"""
        self.post_message(self.AgentEvent(AgentEvents.TOOL_CONFIRMATION_REQUESTED.value, data))

    # --- MESSAGE QUEUE HANDLERS (Called by Textual) ---

    def on_textual_ui_agent_event(self, message: AgentEvent) -> None:
        """
        Handle agent events posted to message queue
        This runs on the UI thread
        """
        event_type = message.event_type
        data = message.data

        # Get chat display widget
        try:
            chat_screen = self.screen_stack[0]
            chat_display = chat_screen.query_one("#chat-display")
        except:
            return

        if event_type == AgentEvents.STREAM_CHUNK.value:
            # Handle streaming content
            chunk = data.get("chunk", "")
            thinking = data.get("thinking")

            if thinking:
                chat_display.add_thinking(thinking)
            elif chunk:
                chat_display.add_message("agent", chunk)

        elif event_type == AgentEvents.RESPONSE_COMPLETE.value:
            # Response complete - add newline
            chat_display.write("")

        elif event_type == AgentEvents.TOOL_RESULT.value:
            # Handle tool result
            result = data.get("result")
            tool_name = data.get("tool_name", "Unknown")
            if hasattr(result, "output"):
                chat_display.add_tool_result(tool_name, result.output, result.success)
            else:
                chat_display.add_tool_result(tool_name, str(result), True)

        elif event_type == AgentEvents.ERROR.value:
            # Handle error
            message = data.get("message", "Unknown error")
            chat_display.add_message("error", message)

        elif event_type == AgentEvents.WARNING.value:
            # Handle warning
            message = data.get("message", "Unknown warning")
            chat_display.add_message("system", f"Warning: {message}")

        elif event_type == AgentEvents.INFO.value:
            # Handle info
            message = data.get("message", "")
            if message:
                chat_display.add_message("system", message)

        elif event_type == AgentEvents.THINKING_STARTED.value:
            # Thinking started
            message = data.get("message", "Thinking...")
            chat_display.add_thinking(message)

        elif event_type == AgentEvents.THINKING_STOPPED.value:
            # Thinking stopped
            chat_display.write("")

    # --- WORKER FOR AGENT PROCESSING ---

    @work(exclusive=True, exit_on_error=False)
    async def process_agent_request(self, user_input: str) -> None:
        """
        Process user input with agent
        Runs in background worker to not block UI
        """
        # TODO: Connect to actual agent
        # For now, just echo back
        await asyncio.sleep(0.5)
        self.post_message(self.AgentEvent(AgentEvents.STREAM_CHUNK.value, {"chunk": f"Echo: {user_input}"}))
        self.post_message(self.AgentEvent(AgentEvents.RESPONSE_COMPLETE.value, {}))