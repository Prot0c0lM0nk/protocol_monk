"""
ui/textual/interface.py
The Bridge: Connects the Async EventBus to the Textual App Loop.
"""

import asyncio
from typing import Dict, Any

from ui.base import UI, ToolResult
from agent.events import AgentEvents, get_event_bus
from .screens.modals.tool_confirm import ToolConfirmModal
from .messages import (
    AgentStreamChunk,
    AgentThinkingStatus,
    AgentToolResult,
    AgentSystemMessage,
    AgentStatusUpdate,  # <--- NEW
)


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
        # 1. Output (Passive)
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
        self._event_bus.subscribe(
            AgentEvents.RESPONSE_COMPLETE.value, self._on_response_complete
        )

    # --- EVENT HANDLERS ---

    async def _on_stream_chunk(self, data: Dict[str, Any]):
        self.app.post_message(AgentStreamChunk(data.get("chunk", "")))

    async def _on_thinking_started(self, data: Dict[str, Any]):
        self.app.post_message(AgentThinkingStatus(is_thinking=True))

    async def _on_thinking_stopped(self, data: Dict[str, Any]):
        self.app.post_message(AgentThinkingStatus(is_thinking=False))
        # === NEW: PULL STATUS UPDATE ===
        # Every time thinking stops, we update the status bar (tokens/context)
        await self._refresh_status()

    async def _refresh_status(self):
        """Pull fresh stats from agent and push to UI."""
        if hasattr(self.app, "agent") and self.app.agent:
            stats = await self.app.agent.get_status()
            self.app.post_message(AgentStatusUpdate(stats))

    async def _on_tool_result(self, data: Dict[str, Any]):
        res = data.get("result")
        name = data.get("tool_name", "Unknown")
        if res is None:
            res = ToolResult(success=False, output="No result data", tool_name=name)
        elif not hasattr(res, "success"):
            res = ToolResult(
                success=data.get("success", True),
                output=str(data.get("output", "")),
                tool_name=name,
            )
        self.app.post_message(AgentToolResult(name, res))
        self.app.post_message(AgentThinkingStatus(is_thinking=True))

    async def _on_error(self, data: Dict[str, Any]):
        msg = data.get("message", "Unknown Error")
        self.app.post_message(AgentSystemMessage(msg, type="error"))

    async def _on_info(self, data: Dict[str, Any]):
        msg = data.get("message", "")
        self.app.post_message(AgentSystemMessage(msg, type="info"))

    async def _on_response_complete(self, data: Dict[str, Any]):
        self.app.post_message(AgentSystemMessage("", type="response_complete"))

    # --- BLOCKING INTERACTION ---

    async def get_input(self) -> str:
        if hasattr(self.app, "get_user_input_wait"):
            return await self.app.get_user_input_wait()
        return ""

    async def prompt_user(self, prompt: str) -> str:
        """
        Called by CommandDispatcher (e.g. for /model selection).
        Reuses the main input bar to get a response.
        """
        # 1. Show the prompt in the chat so user knows what to do
        self.app.post_message(AgentSystemMessage(f"❓ {prompt}", type="info"))

        # 2. Wait for input using the existing mechanism
        # Since the Agent loop is paused inside 'dispatch', this is safe.
        if hasattr(self.app, "get_user_input_wait"):
            return await self.app.get_user_input_wait()
        return ""

    async def confirm_tool_execution(self, tool_data: Dict[str, Any]) -> bool:
        from .screens.modals.tool_confirm import ToolConfirmModal

        if hasattr(self.app, "push_screen_wait"):
            return await self.app.push_screen_wait(ToolConfirmModal(tool_data))
        return True

    # --- REQUIRED STUBS ---
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
