"""
ui/plain/interface.py - The Controller Layer
"""

import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime

from ui.base import UI
from agent.events import AgentEvents, get_event_bus
from tools.base import ToolResult

from .renderer import PlainRenderer
from .input import InputManager

class PlainUI(UI):
    """
    Event-Driven Plain CLI - Standard Output Aesthetic
    """

    def __init__(self):
        super().__init__()
        self.auto_confirm = False
        
        # Components
        self.renderer = PlainRenderer()
        self.input = InputManager()
        
        # Event Bus
        self._event_bus = get_event_bus()
        
        # State Machine
        self._is_busy = False          
        self._state_change_event = asyncio.Event()
        
        # Pending Tool Confirmation
        self._pending_confirmation: Optional[Dict[str, Any]] = None
        
        # Stream Buffer
        self._stream_line_buffer = ""
        self._in_thinking_block = False
        
        self._setup_event_listeners()

    def _setup_event_listeners(self):
        self._event_bus.subscribe(AgentEvents.STATUS_CHANGED.value, self._on_status_changed)
        self._event_bus.subscribe(AgentEvents.TOOL_CONFIRMATION_REQUESTED.value, self._on_tool_confirmation_requested)
        self._event_bus.subscribe(AgentEvents.ERROR.value, self._on_agent_error)
        self._event_bus.subscribe(AgentEvents.WARNING.value, self._on_agent_warning)
        self._event_bus.subscribe(AgentEvents.INFO.value, self._on_agent_info)
        self._event_bus.subscribe(AgentEvents.THINKING_STARTED.value, self._on_thinking_started)
        self._event_bus.subscribe(AgentEvents.THINKING_STOPPED.value, self._on_thinking_stopped)
        self._event_bus.subscribe(AgentEvents.TOOL_EXECUTION_START.value, self._on_tool_start)
        self._event_bus.subscribe(AgentEvents.TOOL_EXECUTION_PROGRESS.value, self._on_tool_progress)
        self._event_bus.subscribe(AgentEvents.TOOL_EXECUTION_COMPLETE.value, self._on_tool_complete)
        self._event_bus.subscribe(AgentEvents.TOOL_ERROR.value, self._on_tool_error)
        self._event_bus.subscribe(AgentEvents.TOOL_RESULT.value, self._on_tool_result)
        self._event_bus.subscribe(AgentEvents.STREAM_CHUNK.value, self._on_stream_chunk)
        self._event_bus.subscribe(AgentEvents.RESPONSE_COMPLETE.value, self._on_response_complete)
        self._event_bus.subscribe(AgentEvents.CONTEXT_OVERFLOW.value, self._on_context_overflow)
        self._event_bus.subscribe(AgentEvents.MODEL_SWITCHED.value, self._on_model_switched)
        self._event_bus.subscribe(AgentEvents.PROVIDER_SWITCHED.value, self._on_provider_switched)
        self._event_bus.subscribe(AgentEvents.COMMAND_RESULT.value, self._on_command_result)

    # ============================================================
    # INTERRUPTIBLE INPUT LOOP
    # ============================================================

    async def run_async(self):
        self.renderer.print_startup_banner()

        try:
            while True:
                # ------------------------------------------------
                # 1. PRIORITY: Handle Tool Confirmation
                # ------------------------------------------------
                if self._pending_confirmation:
                    await self._handle_confirmation_prompt()
                    continue

                # ------------------------------------------------
                # 2. STATE: Wait if Busy (with timeout for safety)
                # ------------------------------------------------
                if self._is_busy:
                    try:
                        # Wait with timeout to prevent permanent lockup
                        await asyncio.wait_for(self._state_change_event.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        # Timeout - force reset to prevent lockup
                        self._is_busy = False
                        self.renderer.print_warning("UI: Timeout waiting for agent, forcing reset")
                    self._state_change_event.clear()
                    continue

                # ------------------------------------------------
                # 3. IDLE: Wait for state change events (with timeout)
                # ------------------------------------------------
                # NOTE: We do NOT wait for input here!
                # The agent calls ui.get_input() when it needs user input.
                # We only wait for events like tool confirmations.
                try:
                    await asyncio.wait_for(self._state_change_event.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    # Timeout - just continue the loop
                    pass
                self._state_change_event.clear()

        except KeyboardInterrupt:
            self.renderer.print_system("Shutting down...")
        except Exception as e:
            self.renderer.print_error(f"Fatal UI Error: {e}")
    async def _handle_confirmation_prompt(self):
        """Helper to manage the confirmation interaction"""
        tool_data = self._pending_confirmation
        self.renderer.render_tool_confirmation(
            tool_data["tool_name"],
            tool_data["params"]
        )

        user_ans = await self.input.read_input("Approve execution? (y/n)")
        
        if user_ans is None: # Ctrl+C
            self.renderer.print_system("Cancelled.")
            self._pending_confirmation = None
            # Set busy to False so UI returns to idle state
            self._is_busy = False
            return

        approved = user_ans.lower().startswith('y')

        if approved:
            self.renderer.print_system(f"✓ Approved {tool_data['tool_name']}")
        else:
            self.renderer.print_error(f"✗ Rejected {tool_data['tool_name']}")

        await self._event_bus.emit(
            "ui.tool_confirmation",
            {
                "tool_call_id": tool_data["tool_call_id"],
                "approved": approved
            }
        )
        
        self._pending_confirmation = None
        # Agent will now execute the tool, so set busy state
        # The agent will emit STATUS_CHANGED or TOOL_EXECUTION_START which will also set busy
        # But we set it here to be safe
        self._is_busy = True
    # ============================================================
    # Event Handlers
    # ============================================================

    async def _on_status_changed(self, data: Dict[str, Any]):
        """Master Switch for UI Locking."""
        status = data.get("status", "")
        if status == "working":
            self._is_busy = True
        elif status == "idle":
            if not self._pending_confirmation:
                self._is_busy = False
        # ALWAYS wake the loop on status change so we can re-evaluate priorities
        self._state_change_event.set()
    async def _on_tool_confirmation_requested(self, data: Dict[str, Any]):
        await self._flush_stream_buffer()
        tool_call = data.get("tool_call", {})
        self._pending_confirmation = {
            "tool_call_id": data.get("tool_call_id"),
            "tool_name": tool_call.get("action", "Unknown Tool"),
            "params": tool_call.get("parameters", {})
        }
        # CRITICAL: Clear busy state so main loop can process confirmation
        # Agent is waiting for user input, not actively processing
        self._is_busy = False
        # Wake up the loop to cancel any active input prompt
        self._state_change_event.set()
    async def _on_response_complete(self, data: Dict[str, Any]):
        if self._stream_line_buffer:
            await self._print_stream_line(
                self._stream_line_buffer, is_thinking=self._in_thinking_block
            )
            self._stream_line_buffer = ""
        self.renderer.console.print()
        self.renderer.reset_thinking_state()
        
        # Agent finished processing - clear busy state and wake up main loop
        self._is_busy = False
        self._state_change_event.set()

    async def _on_tool_start(self, data: Dict[str, Any]):
        self._is_busy = True
        await self._flush_stream_buffer()
        if "tools" in data and isinstance(data["tools"], list):
            names = ", ".join(data["tools"])
            self.renderer.print_system(f"Executing: {names}...")
        else:
            tool_name = data.get("tool_name", "Unknown tool")
            self.renderer.print_system(f"Executing: {tool_name}...")

    async def _on_agent_error(self, data: Dict[str, Any]):
        self.renderer.print_error(data.get("message", "Unknown error"))
        self._is_busy = False
        self._state_change_event.set()

    async def _on_command_result(self, data: Dict[str, Any]):
        self._is_busy = True
        success = data.get("success", True)
        message = data.get("message", "")
        if message:
            if success: await self.print_info(message)
            else: await self.print_error(message)

    # ... (Rest of handlers: warning, info, thinking, tool_result, stream, context, etc. remain unchanged) ...
    
    async def _on_agent_warning(self, data: Dict[str, Any]):
        self.renderer.print_warning(data.get("message", "Unknown warning"))

    async def _on_agent_info(self, data: Dict[str, Any]):
        message = data.get("message", "")
        payload = data.get("data")
        if message.strip(): self.renderer.print_system(message)
        if payload and isinstance(payload, list): self.renderer.render_info_list(payload)

    async def _on_thinking_started(self, data: Dict[str, Any]):
        self.renderer.start_thinking(data.get("message", "Thinking..."))

    async def _on_thinking_stopped(self, data: Dict[str, Any]):
        self.renderer.stop_thinking()

    async def _on_tool_progress(self, data: Dict[str, Any]): pass
    async def _on_tool_complete(self, data: Dict[str, Any]): pass

    async def _on_tool_error(self, data: Dict[str, Any]):
        self.renderer.print_error(f"Tool Error ({data.get('tool_name')}): {data.get('error')}")

    async def _on_tool_result(self, data: Dict[str, Any]):
        tool_name = data.get("tool_name", "Unknown tool")
        result = data.get("result", "")
        
        # Extract output from ToolResult object (tools.base.ToolResult)
        if hasattr(result, 'output'):
            # It's a tools.base.ToolResult object
            output = result.output
        elif isinstance(result, dict) and 'output' in result:
            # It's a dict with output field
            output = result['output']
        else:
            # Fallback: convert to string
            output = str(result)
        
        # Create UI ToolResult for rendering
        tr = ToolResult(True, output, tool_name)
        self.renderer.render_tool_result(tool_name, tr)

    async def _on_stream_chunk(self, data: Dict[str, Any]):
        thinking_chunk = data.get("thinking")
        answer_chunk = data.get("chunk", "")
        
        if thinking_chunk:
            self._in_thinking_block = True
            self._stream_line_buffer += thinking_chunk
        elif answer_chunk:
            if self._in_thinking_block:
                if self._stream_line_buffer:
                    self.renderer.render_line(self._stream_line_buffer, is_thinking=True)
                    self._stream_line_buffer = ""
                self.renderer.console.print()
                self._in_thinking_block = False
            self._stream_line_buffer += answer_chunk
        
        while "\n" in self._stream_line_buffer:
            line, self._stream_line_buffer = self._stream_line_buffer.split("\n", 1)
            self.renderer.render_line(line, is_thinking=self._in_thinking_block)

    async def _on_context_overflow(self, data: Dict[str, Any]):
        self.renderer.print_warning(f"Context: {data.get('current_tokens')}/{data.get('max_tokens')}")

    async def _on_model_switched(self, data: Dict[str, Any]):
        self.renderer.print_system(f"Model: {data.get('old_model')} → {data.get('new_model')}")

    async def _on_provider_switched(self, data: Dict[str, Any]):
        self.renderer.print_system(f"Provider: {data.get('old_provider')} → {data.get('new_provider')}")

    # --- UI Base Implementation ---
    async def print_stream(self, text: str):
        async with self._lock: self.renderer.print_stream(text)
    async def print_error(self, message: str):
        async with self._lock: self.renderer.print_error(message)
    async def print_info(self, message: str):
        async with self._lock: self.renderer.print_system(message)
    async def start_thinking(self):
        async with self._lock: self.renderer.start_thinking()
    async def stop_thinking(self):
        async with self._lock: self.renderer.stop_thinking()
    async def prompt_user(self, prompt: str) -> str:
        return await self.input.read_input(prompt_text=prompt)
    async def display_selection_list(self, title: str, items: List[Any]) -> Any:
        async with self._lock:
            self.renderer.print_system(title)
            self.renderer.render_info_list(items)
        while True:
            choice = await self.input.read_input("Select #")
            if choice is None: return None
            try:
                index = int(choice) - 1
                if 0 <= index < len(items): return items[index]
            except ValueError: pass
            async with self._lock: self.renderer.print_error("Invalid selection")
    async def display_tool_result(self, result: ToolResult):
        self.renderer.render_tool_result(result.tool_name or "Tool", result)
    async def get_input(self) -> str:
        """
        Get user input for main interaction loop.
        CRITICAL: Check for pending confirmations first!
        """
        # Priority 1: Handle pending tool confirmation
        if self._pending_confirmation:
            await self._handle_confirmation_prompt()
            # After handling confirmation, we're busy (agent executing tool)
            # Return empty to let agent continue, don't wait for more input
            return ""
    async def confirm_action(self, message: str) -> bool:
        """Confirm action with yes/no prompt (with timeout)"""
        try:
            response = await asyncio.wait_for(
                self.input.read_input(f"{message} (y/n)"),
                timeout=30.0
            )
            return response.lower().startswith("y") if response else False
        except asyncio.TimeoutError:
            self.renderer.print_warning("Confirmation timeout - defaulting to no")
            return False
    async def get_input(self) -> str:
        """
        Get user input for main interaction loop.
        CRITICAL: Check for pending confirmations first!
        """
        # Priority 1: Handle pending tool confirmation
        if self._pending_confirmation:
            await self._handle_confirmation_prompt()
            # After handling confirmation, we're busy (agent executing tool)
            # Return empty to let agent continue, don't wait for more input
            return ""
        
        # Priority 2: Normal user input (with timeout to prevent lockup)
        try:
            res = await asyncio.wait_for(
                self.input.read_input(is_main_loop=True),
                timeout=30.0  # 30 second timeout
            )
            return res if res is not None else ""
        except asyncio.TimeoutError:
            # Timeout - return empty to let agent continue
            self.renderer.print_warning("Input timeout - returning to agent")
            return ""
    async def _print_stream_line(self, line: str, is_thinking: bool = False):
        async with self._lock:
            self.renderer.render_line(line, is_thinking)