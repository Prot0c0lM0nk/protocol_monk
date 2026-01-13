"""
ui/textual/interface.py
The Bridge: Connects the Async EventBus to the Textual App Loop.
"""

import asyncio
from typing import Dict, Any

from ui.base import UI, ToolResult
from agent.events import AgentEvents, get_event_bus
from .messages import (
    AgentStreamChunk,
    AgentThinkingStatus,
    AgentToolResult,
    AgentSystemMessage,
)

# Late import handling for screens to avoid circular imports
# We rely on the App instance having a 'push_screen_wait' method.


class TextualUI(UI):
    def __init__(self, app):
        """
        Args:
            app: The running ProtocolMonkApp instance.
        """
        super().__init__()
        self.app = app
        self._event_bus = get_event_bus()
        self._setup_event_listeners()

    def _setup_event_listeners(self):
        # 1. Output (Passive) - We just Post Messages to the App
        self._event_bus.subscribe(AgentEvents.STREAM_CHUNK.value, self._on_stream_chunk)
        self._event_bus.subscribe(
            AgentEvents.THINKING_STARTED.value, self._on_thinking_started
        )
        self._event_bus.subscribe(
            AgentEvents.THINKING_STOPPED.value, self._on_thinking_stopped
        )
        self._event_bus.subscribe(AgentEvents.TOOL_RESULT.value, self._on_tool_result)
        self._event_bus.subscribe(AgentEvents.ERROR.value, self._on_error)
        self._event_bus.subscribe(AgentEvents.INFO.value, self._on_info)

        # 2. Lifecycle
        self._event_bus.subscribe(
            AgentEvents.RESPONSE_COMPLETE.value, self._on_response_complete
        )

    # --- EVENT HANDLERS (Bridge to App) ---

    async def _on_stream_chunk(self, data: Dict[str, Any]):
        # Fire and forget - let Textual handle the rendering
        self.app.post_message(AgentStreamChunk(data.get("chunk", "")))

    async def _on_thinking_started(self, data: Dict[str, Any]):
        self.app.post_message(AgentThinkingStatus(is_thinking=True))

    async def _on_thinking_stopped(self, data: Dict[str, Any]):
        self.app.post_message(AgentThinkingStatus(is_thinking=False))

    async def _on_tool_result(self, data: Dict[str, Any]):
        # Unpack or construct ToolResult
        res = data.get("result")
        name = data.get("tool_name", "Unknown")

        # Robust reconstruction if it's a raw dict (common in EDA serialization)
        if not hasattr(res, "success"):
            res = ToolResult(
                success=data.get("success", True),
                output=str(data.get("output", "")),
                tool_name=name,
            )

        self.app.post_message(AgentToolResult(name, res))

    async def _on_error(self, data: Dict[str, Any]):
        msg = data.get("message", "Unknown Error")
        self.app.post_message(AgentSystemMessage(msg, type="error"))

    async def _on_info(self, data: Dict[str, Any]):
        msg = data.get("message", "")
        self.app.post_message(AgentSystemMessage(msg, type="info"))

    async def _on_response_complete(self, data: Dict[str, Any]):
        # Signal UI that generation is done
        self.app.post_message(AgentSystemMessage("", type="response_complete"))

    # --- BLOCKING INTERACTION (The Hard Part) ---

    async def get_input(self) -> str:
        """
        Called by Agent when it needs user input.
        Relies on App having 'get_user_input_wait'.
        """
        if hasattr(self.app, "get_user_input_wait"):
            return await self.app.get_user_input_wait()
        return ""

    async def confirm_tool_execution(self, tool_data: Dict[str, Any]) -> bool:
        """
        Called by Agent to confirm action.
        Relies on App having 'push_screen_wait'.
        """
        # Import here to avoid circular dependency at module level
        from .screens.tool_confirm import ToolConfirmModal

        if hasattr(self.app, "push_screen_wait"):
            # This blocks the Agent task until the UI Modal is dismissed
            return await self.app.push_screen_wait(ToolConfirmModal(tool_data))

        return True  # Fallback

    # --- REQUIRED STUBS (Base Class Compliance) ---
    async def print_stream(self, text: str):
        self.app.post_message(AgentStreamChunk(text))

    async def print_error(self, msg: str):
        self.app.post_message(AgentSystemMessage(msg, type="error"))

    async def print_info(self, msg: str):
        self.app.post_message(AgentSystemMessage(msg, type="info"))

    async def start_thinking(self):
        self.app.post_message(AgentThinkingStatus(True))

    async def stop_thinking(self):
        self.app.post_message(AgentThinkingStatus(False))