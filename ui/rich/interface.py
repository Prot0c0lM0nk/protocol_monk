"""
ui/rich/interface.py
The Rich UI Controller.
"""
import asyncio
from typing import Dict, Any

from ui.base import UI
from ui.prompts import AsyncPrompt
from agent.events import AgentEvents, get_event_bus
from .renderer import RichRenderer
from .input import RichInput

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
        self._event_bus.subscribe(AgentEvents.RESPONSE_COMPLETE.value, self._on_response_complete)
        self._event_bus.subscribe(AgentEvents.THINKING_STARTED.value, self._on_thinking_started)
        self._event_bus.subscribe(AgentEvents.THINKING_STOPPED.value, self._on_thinking_stopped)
        self._event_bus.subscribe(AgentEvents.TOOL_RESULT.value, self._on_tool_result)
        self._event_bus.subscribe(AgentEvents.ERROR.value, self._on_error)
        
        # Lifecycle
        self._event_bus.subscribe(AgentEvents.TASK_COMPLETE.value, self._on_task_complete)

    # --- EVENT HANDLERS ---
    async def _on_stream_chunk(self, data: Dict[str, Any]):
        chunk = data.get("chunk", "")
        self.renderer.update_streaming(chunk)

    async def _on_response_complete(self, data: Dict[str, Any]):
        self.renderer.end_streaming()

    async def _on_thinking_started(self, data: Dict[str, Any]):
        self.renderer.start_thinking()

    async def _on_thinking_stopped(self, data: Dict[str, Any]):
        self.renderer.stop_thinking()

    async def _on_tool_result(self, data: Dict[str, Any]):
        # Data structure: {'tool_name': str, 'result': ToolResult}
        # Note: EDA event payload might differ slightly, checking 'result' object
        res = data.get("result")
        name = data.get("tool_name", "Unknown")
        # Ensure we have a ToolResult object
        if not hasattr(res, 'success'):
             # Fallback if raw dict
             from ui.base import ToolResult
             res = ToolResult(success=True, output=str(res), tool_name=name)
        
        self.renderer.render_tool_result(res, name)

    async def _on_error(self, data: Dict[str, Any]):
        self.renderer.print_error(data.get("message", "Unknown Error"))
        
    async def _on_task_complete(self, data: Dict[str, Any]):
        self.renderer.end_streaming()

    # --- BLOCKING INTERFACE (Called by Agent) ---
    
    async def get_input(self) -> str:
        """Main Loop Input."""
        self.renderer.end_streaming()
        return await self.input.get_input("User Input")

    async def confirm_tool_execution(self, tool_data: Dict[str, Any]) -> bool:
        """Permission Gate."""
        tool_name = tool_data.get("tool_name", "Unknown")
        params = tool_data.get("parameters", {})
        
        # 1. Show the Confirmation Panel
        self.renderer.render_tool_confirmation(tool_name, params)
        
        # 2. Ask via AsyncPrompt (so we don't block event loop if we had one)
        return await AsyncPrompt.confirm("Execute this action?", default=False)
    
    # --- REQUIRED STUBS ---
    async def print_stream(self, text: str): self.renderer.update_streaming(text)
    async def print_error(self, msg: str): self.renderer.print_error(msg)
    async def print_info(self, msg: str): self.renderer.print_system(msg)
    async def start_thinking(self): self.renderer.start_thinking()
    async def stop_thinking(self): self.renderer.stop_thinking()