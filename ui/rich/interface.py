"""
ui/rich/interface.py
The Rich UI Controller.
"""

import asyncio
from typing import Dict, Any, List

from ui.base import UI, ToolResult
from ui.prompts import AsyncPrompt
from agent.events import AgentEvents, get_event_bus
from .renderer import RichRenderer
from .input import RichInput
from .styles import console


class RichUI(UI):
    def __init__(self):
        super().__init__()
        self.renderer = RichRenderer()
        self.input = RichInput()
        self._event_bus = get_event_bus()
        self._setup_event_listeners()

    def _setup_event_listeners(self):
        # Passive Output Listeners
        self._event_bus.subscribe(AgentEvents.STREAM_CHUNK.value, self._on_stream_chunk)
        self._event_bus.subscribe(
            AgentEvents.RESPONSE_COMPLETE.value, self._on_response_complete
        )
        self._event_bus.subscribe(
            AgentEvents.THINKING_STARTED.value, self._on_thinking_started
        )
        self._event_bus.subscribe(
            AgentEvents.THINKING_STOPPED.value, self._on_thinking_stopped
        )
        self._event_bus.subscribe(AgentEvents.TOOL_RESULT.value, self._on_tool_result)

        # Error / Info / Status
        self._event_bus.subscribe(AgentEvents.ERROR.value, self._on_error)
        self._event_bus.subscribe(AgentEvents.WARNING.value, self._on_warning)
        self._event_bus.subscribe(AgentEvents.INFO.value, self._on_info)

        # Slash Commands
        self._event_bus.subscribe(
            AgentEvents.COMMAND_RESULT.value, self._on_command_result
        )

        # Lifecycle
        self._event_bus.subscribe(
            AgentEvents.TASK_COMPLETE.value, self._on_task_complete
        )
        self._event_bus.subscribe(
            AgentEvents.MODEL_SWITCHED.value, self._on_model_switched
        )
        self._event_bus.subscribe(
            AgentEvents.PROVIDER_SWITCHED.value, self._on_provider_switched
        )

    # --- EVENT HANDLERS ---
    async def _on_stream_chunk(self, data: Dict[str, Any]):
        # Handle Reasoning (Thinking)
        thinking = data.get("thinking")
        if thinking:
            self.renderer.update_streaming(thinking, is_thinking=True)
            return

        # Handle Standard Content
        chunk = data.get("chunk", "")
        if chunk:
            self.renderer.update_streaming(chunk, is_thinking=False)

    async def _on_response_complete(self, data: Dict[str, Any]):
        self.renderer.end_streaming()

    async def _on_thinking_started(self, data: Dict[str, Any]):
        self.renderer.start_thinking(data.get("message", "Contemplating..."))

    async def _on_thinking_stopped(self, data: Dict[str, Any]):
        self.renderer.stop_thinking()

    async def _on_tool_result(self, data: Dict[str, Any]):
        res = data.get("result")
        name = data.get("tool_name", "Unknown")
        if not hasattr(res, "success"):
            from ui.base import ToolResult

            res = ToolResult(success=True, output=str(res), tool_name=name)
        self.renderer.render_tool_result(res, name)

    async def _on_error(self, data: Dict[str, Any]):
        self.renderer.print_error(data.get("message", "Unknown Error"))

    async def _on_warning(self, data: Dict[str, Any]):
        self.renderer.print_system(f"[warning]Warning:[/] {data.get('message', '')}")

    async def _on_info(self, data: Dict[str, Any]):
        msg = data.get("message", "")
        context = data.get("context", "")
        items = data.get("data", [])

        if context in ["model_selection", "provider_selection"] and items:
            await self.display_selection_list(msg, items)
        elif msg.strip():
            self.renderer.print_system(msg)

    async def _on_command_result(self, data: Dict[str, Any]):
        success = data.get("success", True)
        message = data.get("message", "")
        if message:
            self.renderer.render_command_result(success, message)

    async def _on_task_complete(self, data: Dict[str, Any]):
        self.renderer.end_streaming()

    async def _on_model_switched(self, data: Dict[str, Any]):
        self.renderer.print_system(f"Model Switched: {data.get('new_model')}")

    async def _on_provider_switched(self, data: Dict[str, Any]):
        self.renderer.print_system(f"Provider Switched: {data.get('new_provider')}")

    # --- BLOCKING INTERFACE ---

    async def get_input(self) -> str:
        self.renderer.end_streaming()
        # We assume the user sees the list above and just types the number here
        return await self.input.get_input("User Input")

    async def confirm_tool_execution(self, tool_data: Dict[str, Any]) -> bool:
        tool_name = tool_data.get("tool_name", "Unknown")
        params = tool_data.get("parameters", {})

        self.renderer.render_tool_confirmation(tool_name, params)

        return await AsyncPrompt.confirm(
            "[monk.text]Execute this action?[/]", default=False, console=console
        )

    # --- VISUALS ---
    async def display_startup_banner(self, greeting: str):
        self.renderer.render_banner(greeting)

    async def display_selection_list(self, title: str, items: List[Any]):
        """Just render the list. Input is handled by main loop."""
        self.renderer.render_selection_list(title, items)

    async def display_tool_result(self, result: ToolResult, tool_name: str):
        self.renderer.render_tool_result(result, tool_name)

    async def shutdown(self):
        self.renderer.end_streaming()
        self.renderer.stop_thinking()
        console.show_cursor(True)

    # --- REQUIRED STUBS ---
    async def print_stream(self, text: str):
        self.renderer.update_streaming(text)

    async def print_error(self, msg: str):
        self.renderer.print_error(msg)

    async def print_info(self, msg: str):
        self.renderer.print_system(msg)

    async def start_thinking(self):
        self.renderer.start_thinking()

    async def stop_thinking(self):
        self.renderer.stop_thinking()

    async def run_async(self):
        await asyncio.Event().wait()
