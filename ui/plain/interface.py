"""
ui/plain/interface.py
"""

import asyncio
from typing import Any, Dict, List
from ui.base import UI, ToolResult
from agent.events import AgentEvents, get_event_bus
from .renderer import PlainRenderer
from .input import InputManager


class PlainUI(UI):
    def __init__(self):
        super().__init__()
        self.renderer = PlainRenderer()
        self.input = InputManager()
        self._event_bus = get_event_bus()
        self._stream_line_buffer = ""
        self._in_thinking_block = False
        self._setup_event_listeners()

    def _setup_event_listeners(self):
        # We ONLY listen for passive output events now.
        # Active control (Input/Confirmation) is handled via direct calls.
        self._event_bus.subscribe(AgentEvents.STREAM_CHUNK.value, self._on_stream_chunk)
        self._event_bus.subscribe(
            AgentEvents.RESPONSE_COMPLETE.value, self._on_response_complete
        )
        self._event_bus.subscribe(AgentEvents.TOOL_RESULT.value, self._on_tool_result)
        self._event_bus.subscribe(AgentEvents.ERROR.value, self._on_agent_error)
        self._event_bus.subscribe(AgentEvents.WARNING.value, self._on_agent_warning)
        self._event_bus.subscribe(AgentEvents.INFO.value, self._on_agent_info)
        self._event_bus.subscribe(
            AgentEvents.THINKING_STARTED.value, self._on_thinking_started
        )
        self._event_bus.subscribe(
            AgentEvents.THINKING_STOPPED.value, self._on_thinking_stopped
        )
        self._event_bus.subscribe(
            AgentEvents.CONTEXT_OVERFLOW.value, self._on_context_overflow
        )
        self._event_bus.subscribe(
            AgentEvents.MODEL_SWITCHED.value, self._on_model_switched
        )
        self._event_bus.subscribe(
            AgentEvents.PROVIDER_SWITCHED.value, self._on_provider_switched
        )
        self._event_bus.subscribe(
            AgentEvents.COMMAND_RESULT.value, self._on_command_result
        )

    # --- BLOCKING METHODS (Called by Agent) ---

    async def get_input(self) -> str:
        """Agent calls this when it wants a command."""
        await self._flush_stream_buffer()
        return await self.input.read_input(is_main_loop=True) or ""

    async def confirm_tool_execution(self, tool_data: Dict[str, Any]) -> bool:
        """Agent calls this when it wants approval."""
        await self._flush_stream_buffer()

        tool_name = tool_data.get("tool_name", "Unknown")
        params = tool_data.get("parameters", {})

        # 1. Render the Prompt
        self.renderer.render_tool_confirmation(tool_name, params)

        # 2. Block for Input
        user_ans = await self.input.read_input("Approve execution? (y/n)")

        if user_ans is None:
            return False  # Ctrl+C

        approved = user_ans.lower().startswith("y")

        if approved:
            self.renderer.print_system(f"✓ Approved {tool_name}")
        else:
            self.renderer.print_error(f"✗ Rejected {tool_name}")

        return approved

    # --- EVENT HANDLERS (Passive Output) ---
    async def _on_stream_chunk(self, data: Dict[str, Any]):
        """Hybrid Streaming: Instant Text, Buffered Code"""
        thinking_chunk = data.get("thinking")
        answer_chunk = data.get("chunk", "")

        # 1. Handle Thinking (Keep strict buffering for clean dimming)
        if thinking_chunk:
            self._in_thinking_block = True
            self._stream_line_buffer += thinking_chunk
            while "\n" in self._stream_line_buffer:
                line, self._stream_line_buffer = self._stream_line_buffer.split("\n", 1)
                self.renderer.render_line(line, is_thinking=True)
            return

        # 2. Handle Answer (Hybrid)
        if answer_chunk:
            # If we were previously thinking, flush that state first
            if self._in_thinking_block:
                if self._stream_line_buffer:
                    self.renderer.render_line(
                        self._stream_line_buffer, is_thinking=True
                    )
                    self._stream_line_buffer = ""
                self.renderer.console.print()
                self._in_thinking_block = False

            # Heuristic: If we see code fences, switch to buffering
            # (Use renderer state if available, or track locally)
            if "```" in answer_chunk or self.renderer._in_code_block:
                self._stream_line_buffer += answer_chunk
                while "\n" in self._stream_line_buffer:
                    line, self._stream_line_buffer = self._stream_line_buffer.split(
                        "\n", 1
                    )
                    self.renderer.render_line(line, is_thinking=False)
            else:
                # FAST PATH: Print text instantly!
                # If we have a leftover buffer from a previous partial line, print it first
                if self._stream_line_buffer:
                    self.renderer.print_stream(self._stream_line_buffer)
                    self._stream_line_buffer = ""

                self.renderer.print_stream(answer_chunk)

    async def _on_response_complete(self, data: Dict[str, Any]):
        await self._flush_stream_buffer()
        self.renderer.console.print()
        self.renderer.reset_thinking_state()

    async def _on_tool_result(self, data: Dict[str, Any]):
        result = data.get("result", "")
        tool_name = data.get("tool_name", "Unknown")
        output = result.output if hasattr(result, "output") else str(result)
        self.renderer.render_tool_result(tool_name, ToolResult(True, output, tool_name))

    async def _on_agent_error(self, data: Dict[str, Any]):
        self.renderer.print_error(data.get("message", "Unknown error"))

    async def _on_agent_warning(self, data: Dict[str, Any]):
        self.renderer.print_warning(data.get("message", "Unknown warning"))

    async def _on_agent_info(self, data: Dict[str, Any]):
        msg = data.get("message", "")
        if msg.strip():
            self.renderer.print_system(msg)

    async def _on_thinking_started(self, data: Dict[str, Any]):
        self.renderer.start_thinking(data.get("message", "Thinking..."))

    async def _on_thinking_stopped(self, data: Dict[str, Any]):
        self.renderer.stop_thinking()

    async def _on_context_overflow(self, data: Dict[str, Any]):
        self.renderer.print_warning(
            f"Context: {data.get('current_tokens')}/{data.get('max_tokens')}"
        )

    async def _on_model_switched(self, data: Dict[str, Any]):
        self.renderer.print_system(
            f"Model: {data.get('old_model')} → {data.get('new_model')}"
        )

    async def _on_provider_switched(self, data: Dict[str, Any]):
        self.renderer.print_system(
            f"Provider: {data.get('old_provider')} → {data.get('new_provider')}"
        )

    async def _on_command_result(self, data: Dict[str, Any]):
        success = data.get("success", True)
        message = data.get("message", "")
        if message:
            if success:
                await self.print_info(message)
            else:
                await self.print_error(message)

    # --- HELPER ---
    async def _flush_stream_buffer(self):
        async with self._lock:
            if self._stream_line_buffer:
                self.renderer.render_line(
                    self._stream_line_buffer, is_thinking=self._in_thinking_block
                )
                self._stream_line_buffer = ""

    # --- REQUIRED BY BASE ---
    async def run_async(self):
        self.renderer.print_startup_banner()
        # Keep task alive if needed, but agent drives loop
        await asyncio.Event().wait()

    async def print_stream(self, text: str):
        self.renderer.print_stream(text)

    async def print_error(self, msg: str):
        self.renderer.print_error(msg)

    async def print_info(self, msg: str):
        self.renderer.print_system(msg)

    async def start_thinking(self):
        self.renderer.start_thinking()

    async def stop_thinking(self):
        self.renderer.stop_thinking()
