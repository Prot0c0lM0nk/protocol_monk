"""
ui/textual/interface.py
The Bridge: Connects the Async EventBus to the Textual App Loop.
"""

import asyncio
from typing import Dict, Any, Optional

from ui.base import UI, ToolResult
from agent.events import AgentEvents, EventBus, get_event_bus
from .screens.modals.tool_confirm import ToolConfirmModal
from .messages import (
    AgentStreamChunk,
    AgentThinkingStatus,
    AgentToolResult,
    AgentSystemMessage,
    AgentStatusUpdate,  # <--- NEW
)
from .screens.modals.selection import SelectionModal


class TextualUI(UI):
    def __init__(self, app, event_bus: Optional[EventBus] = None):
        """
        Args:
            app: The running ProtocolMonkApp instance.
        """
        super().__init__()
        self.app = app
        self._event_bus = event_bus or get_event_bus()
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
            AgentEvents.MODEL_SWITCHED.value, self._on_model_switched
        )
        self._event_bus.subscribe(
            AgentEvents.PROVIDER_SWITCHED.value, self._on_provider_switched
        )
        self._event_bus.subscribe(
            AgentEvents.RESPONSE_COMPLETE.value, self._on_response_complete
        )
        self._event_bus.subscribe(
            AgentEvents.INPUT_REQUESTED.value, self._on_input_requested
        )
        self._event_bus.subscribe(
            AgentEvents.TOOL_CONFIRMATION_REQUESTED.value,
            self._on_tool_confirmation_request,
        )

        # Selection tracking for model/provider switches
        self._pending_selection = None
        self._pending_options = None
        self._pending_title = None

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
            stats["working_dir"] = getattr(self.app.agent, "working_dir", "")
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
        items = data.get("data", [])
        context = data.get("context", "")

        if msg:
            # Modal selection for model/provider switches
            if context in ["model_selection", "provider_selection"] and items:
                self._pending_title = msg
                self._pending_options = [self._format_option(item) for item in items]
                return
            self.app.post_message(AgentSystemMessage(msg, type="info"))

    async def _on_model_switched(self, data: Dict[str, Any]):
        old_model = data.get("old_model", "")
        new_model = data.get("new_model", "")
        if hasattr(self.app, "post_message"):
            self.app.post_message(
                AgentSystemMessage(
                    f"🔄 Model switched: {old_model} → {new_model}", type="info"
                )
            )
        try:
            input_bar = self.app.screen.query_one("#msg-input")
            input_bar.focus()
        except Exception:
            pass
        await self._refresh_status()

    async def _on_provider_switched(self, data: Dict[str, Any]):
        old_provider = data.get("old_provider", "")
        new_provider = data.get("new_provider", "")
        if hasattr(self.app, "post_message"):
            self.app.post_message(
                AgentSystemMessage(
                    f"🔄 Provider switched: {old_provider} → {new_provider}",
                    type="info",
                )
            )
        try:
            input_bar = self.app.screen.query_one("#msg-input")
            input_bar.focus()
        except Exception:
            pass
        await self._refresh_status()

    async def _on_response_complete(self, data: Dict[str, Any]):
        self.app.post_message(AgentSystemMessage("", type="response_complete"))

    async def _on_input_requested(self, data: Dict[str, Any]):
        prompt_text = data.get("prompt", "Enter value: ")
        # If a selection list is pending, show modal now and respond
        if self._pending_options:
            title = self._pending_title or "Select an option"
            options = self._pending_options
            self._pending_title = None
            self._pending_options = None

            if hasattr(self.app, "push_screen_wait"):
                selected_index = await self.app.push_screen_wait(
                    SelectionModal(title, options)
                )
                if selected_index is not None:
                    await self._event_bus.emit(
                        AgentEvents.INPUT_RESPONSE.value,
                        {"input": str(selected_index + 1)},
                    )
                    return

        # If we already have a selection from a modal, respond immediately
        if self._pending_selection:
            selection = self._pending_selection
            self._pending_selection = None
            await self._event_bus.emit(
                AgentEvents.INPUT_RESPONSE.value, {"input": selection}
            )
            return

        self.app.post_message(AgentSystemMessage(f"❓ {prompt_text}", type="info"))
        # Ensure input is focused for the prompt
        try:
            input_bar = self.app.screen.query_one("#msg-input")
            input_bar.focus()
        except Exception:
            pass
        if hasattr(self.app, "get_user_input_wait"):
            response = await self.app.get_user_input_wait()
        else:
            response = ""
        await self._event_bus.emit(
            AgentEvents.INPUT_RESPONSE.value, {"input": response or ""}
        )

    def _format_option(self, item) -> str:
        if hasattr(item, "name"):
            name = item.name
        else:
            name = str(item)
        provider = getattr(item, "provider", None)
        if provider:
            name = f"{name} ({provider})"
        return name

    async def _on_tool_confirmation_request(self, data: Dict[str, Any]):
        tool_call = data.get("tool_call", {})
        tool_call_id = data.get("tool_call_id", "")
        tool_name = tool_call.get("action", "Unknown Tool")
        tool_args = tool_call.get("parameters", {})

        approved = True
        if hasattr(self.app, "push_screen_wait"):
            approved = await self.app.push_screen_wait(
                ToolConfirmModal({"tool": tool_name, "args": tool_args})
            )

        await self._event_bus.emit(
            AgentEvents.TOOL_CONFIRMATION_RESPONSE.value,
            {
                "tool_call_id": tool_call_id,
                "approved": approved,
                "edits": None,
            },
        )

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
