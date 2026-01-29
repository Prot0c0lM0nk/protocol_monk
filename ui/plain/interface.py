"""
ui/plain/interface.py
"""

import asyncio
import sys
from typing import Any, Dict, List
from ui.base import UI, ToolResult
from agent.events import AgentEvents, get_event_bus
from .renderer import PlainRenderer
from .input import InputManager
from ..input_safety_wrapper import create_safe_input_manager
from config.static import settings


class PlainUI(UI):
    def __init__(self, event_bus=None):
        super().__init__()
        # 1. Initialize Infrastructure FIRST
        self.renderer = PlainRenderer()
        self._terminal_lock = asyncio.Lock()

        # Use safety wrapper for input handling
        if settings.ui.use_async_input:
            # Use safe input manager that handles both async and fallback
            self.input = create_safe_input_manager("plain", lock=self._terminal_lock)
        else:
            # Use traditional input manager
            self.input = InputManager()
        
        # CRITICAL: Define event_bus before calling setup_listeners
        self._event_bus = event_bus or get_event_bus()
        
        self._stream_line_buffer = ""
        self._in_thinking_block = False
        
        self.turn_complete = asyncio.Event()
        self.running = False
        
        # 2. Setup Listeners LAST (Now safe because self._event_bus exists)
        self._setup_event_listeners()

    def _setup_event_listeners(self):
        # We ONLY listen for passive output events now.
        # Active control (Input/Confirmation) is handled via direct calls.
        self._event_bus.subscribe(AgentEvents.STREAM_CHUNK.value, self._on_stream_chunk)
        self._event_bus.subscribe(AgentEvents.RESPONSE_COMPLETE.value, self._on_response_complete)
        self._event_bus.subscribe(AgentEvents.TOOL_RESULT.value, self._on_tool_result)
        self._event_bus.subscribe(AgentEvents.ERROR.value, self._on_agent_error)
        self._event_bus.subscribe(AgentEvents.WARNING.value, self._on_agent_warning)
        self._event_bus.subscribe(AgentEvents.INFO.value, self._on_agent_info)
        self._event_bus.subscribe(AgentEvents.THINKING_STARTED.value, self._on_thinking_started)
        self._event_bus.subscribe(AgentEvents.THINKING_STOPPED.value, self._on_thinking_stopped)
        self._event_bus.subscribe(AgentEvents.CONTEXT_OVERFLOW.value, self._on_context_overflow)
        self._event_bus.subscribe(AgentEvents.MODEL_SWITCHED.value, self._on_model_switched)
        self._event_bus.subscribe(AgentEvents.PROVIDER_SWITCHED.value, self._on_provider_switched)
        self._event_bus.subscribe(AgentEvents.COMMAND_RESULT.value, self._on_command_result)
        
        # Interactive Requests
        self._event_bus.subscribe(AgentEvents.TOOL_CONFIRMATION_REQUESTED.value, self._on_tool_confirmation_requested)
        self._event_bus.subscribe(AgentEvents.INPUT_REQUESTED.value, self._on_input_requested)
        
        # Startup Banner
        self._event_bus.subscribe(AgentEvents.APP_STARTED.value, self._on_app_started)

    async def _on_app_started(self, data: Dict[str, Any]):
        """Render the startup banner from the data packet."""
        async with self._terminal_lock:
            wd = data.get("working_dir", ".")
            model = data.get("model", "Unknown")
            provider = data.get("provider", "Unknown")

            # The UI controls the formatting (Colors, Layout, Text)
            self.renderer.print_system(f"✠ Protocol Monk started in {wd}")
            self.renderer.print_system(f"Model: {model} ({provider})")
            self.renderer.print_system("Type '/help' for commands, '/quit' to exit.")

    # --- MAIN LOOP ---
    async def stop(self):
        """Stop the UI and cleanup resources."""
        self.running = False

        # Cleanup input manager
        if settings.ui.use_async_input and hasattr(self.input, 'cleanup'):
            await self.input.cleanup()

    async def run_loop(self):
        """The main blocking loop for the application."""
        self.running = True

        # Check if we're in a proper terminal
        if not sys.stdin.isatty():
            self.renderer.print_warning("Not running in a terminal. Input may not work properly.")
            self.renderer.print_warning("Please run this application in a terminal emulator.")
        
        # Initial prompt
        # We don't print anything, just wait for input
        
        while self.running:
            try:
                # 1. Get Input (with safety wrapper)
                if settings.ui.use_async_input:
                    # Use safety wrapper method
                    user_input = await self.input.read_input_safe(is_main_loop=True)
                else:
                    # Use traditional method
                    user_input = await self.input.read_input(is_main_loop=True)
                
                if user_input is None: # EOF/Interrupt
                    break
                    
                if not user_input.strip():
                    continue
                
                if user_input.lower() in ("/quit", "/exit"):
                    await self._event_bus.emit(AgentEvents.INFO.value, {"message": "Shutting down..."})
                    break

                self.turn_complete.clear()

                # 2. Fire Event
                await self._event_bus.emit(AgentEvents.USER_INPUT.value, {"input": user_input})
                
                # 3. Wait for Agent Response
                await self.turn_complete.wait()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Check if this is a terminal-related error
                if "Invalid argument" in str(e) and not sys.stdin.isatty():
                    self.renderer.print_error(f"UI Error: Not running in a proper terminal. Please run in a terminal emulator.")
                    self.renderer.print_error(f"Current environment: stdin.isatty() = {sys.stdin.isatty()}")
                    break
                else:
                    self.renderer.print_error(f"UI Loop Error: {e}")
                    # For terminal errors, give a moment before retrying
                    import time
                    time.sleep(0.1)

        # Cleanup after loop ends
        await self.stop()

    # --- INTERACTIVE HANDLERS (The New Logic) ---
    
    async def _on_tool_confirmation_requested(self, data: Dict[str, Any]):
        """Handle request for tool confirmation."""
        tool_call = data.get("tool_call", {})
        tool_name = tool_call.get("action", "Unknown")
        params = tool_call.get("parameters", {})
        tool_id = data.get("tool_call_id")
        
        # Render under lock
        async with self._terminal_lock:
            await self._flush_stream_buffer()
            self.renderer.render_tool_confirmation(tool_name, params)
        
        # Block for Input
        # Note: input.read_input must handle re-entrancy if needed, 
        # or we rely on the fact that this is called within the event loop
        user_ans = await self.input.read_input("Approve execution? (y/n)")
        
        approved = False
        if user_ans and user_ans.lower().startswith("y"):
            approved = True
            # This print should also be locked
            async with self._terminal_lock:
                self.renderer.print_system(f"✓ Approved {tool_name}")
        else:
            async with self._terminal_lock:
                self.renderer.print_error(f"✗ Rejected {tool_name}")

        # Respond
        await self._event_bus.emit(
            AgentEvents.TOOL_CONFIRMATION_RESPONSE.value, 
            {
                "approved": approved,
                "tool_call_id": tool_id,
                "edits": None # Logic for edits can be added here
            }
        )

    async def _on_input_requested(self, data: Dict[str, Any]):
        """Handle generic input request (e.g. for filename)."""
        prompt = data.get("prompt", "> ")
        async with self._terminal_lock:
            await self._flush_stream_buffer()
        
        user_input = await self.input.read_input(prompt)
        
        await self._event_bus.emit(
            AgentEvents.INPUT_RESPONSE.value,
            {"input": user_input}
        )

    # --- EVENT HANDLERS (Passive Output) ---
    # (These remain largely the same, just keeping them clean)
    async def _on_stream_chunk(self, data: Dict[str, Any]):
        async with self._terminal_lock:
            thinking_chunk = data.get("thinking")
            answer_chunk = data.get("chunk", "")
            
            if thinking_chunk:
                self._in_thinking_block = True
                self._stream_line_buffer += thinking_chunk
                while "\n" in self._stream_line_buffer:
                    line, self._stream_line_buffer = self._stream_line_buffer.split("\n", 1)
                    self.renderer.render_line(line, is_thinking=True)
                return

            if answer_chunk:
                if self._in_thinking_block:
                    if self._stream_line_buffer:
                        self.renderer.render_line(self._stream_line_buffer, is_thinking=True)
                        self._stream_line_buffer = ""
                    self.renderer.console.print()
                    self._in_thinking_block = False

                if "```" in answer_chunk or getattr(self.renderer, "_in_code_block", False):
                    self._stream_line_buffer += answer_chunk
                    while "\n" in self._stream_line_buffer:
                        line, self._stream_line_buffer = self._stream_line_buffer.split("\n", 1)
                        self.renderer.render_line(line, is_thinking=False)
                else:
                    self._stream_line_buffer += answer_chunk
                    while "\n" in self._stream_line_buffer:
                        line, self._stream_line_buffer = self._stream_line_buffer.split("\n", 1)
                        if line.strip():
                            self.renderer.console.print(line.lstrip())
                        else:
                            self.renderer.console.print()

    async def _on_response_complete(self, data: Dict[str, Any]):
        async with self._terminal_lock:
            await self._flush_stream_buffer()
            self.renderer.console.print()
            self.renderer.reset_thinking_state()
        await self.input.display_prompt()
        self.turn_complete.set() # Unblock run_loop

    async def _on_tool_result(self, data: Dict[str, Any]):
        async with self._terminal_lock:
            result = data.get("result")
            tool_name = data.get("tool_name", "Unknown")
            if result:
                output = result.output if hasattr(result, "output") else str(result)
                self.renderer.render_tool_result(tool_name, ToolResult(True, output, tool_name))

    async def _on_agent_error(self, data: Dict[str, Any]):
        async with self._terminal_lock:
            self.renderer.print_error(data.get("message", "Unknown error"))

    async def _on_agent_warning(self, data: Dict[str, Any]):
        async with self._terminal_lock:
            self.renderer.print_warning(data.get("message", "Unknown warning"))

    async def _on_agent_info(self, data: Dict[str, Any]):
        async with self._terminal_lock:
            msg = data.get("message", "")
            context = data.get("context", "")
            items = data.get("data", [])

            if context in ["model_selection", "provider_selection"] and items:
                self.renderer.render_selection_list(msg, items)
            elif msg.strip():
                self.renderer.print_system(msg)

    async def _on_thinking_started(self, data: Dict[str, Any]):
        async with self._terminal_lock:
            self.renderer.start_thinking(data.get("message", "Thinking..."))

    async def _on_thinking_stopped(self, data: Dict[str, Any]):
        async with self._terminal_lock:
            self.renderer.stop_thinking()

    async def _on_context_overflow(self, data: Dict[str, Any]):
        async with self._terminal_lock:
            self.renderer.print_warning(f"Context: {data.get('current_tokens')}/{data.get('max_tokens')}")

    async def _on_model_switched(self, data: Dict[str, Any]):
        async with self._terminal_lock:
            self.renderer.print_system(f"Model: {data.get('old_model')} → {data.get('new_model')}")

    async def _on_provider_switched(self, data: Dict[str, Any]):
        async with self._terminal_lock:
            self.renderer.print_system(f"Provider: {data.get('old_provider')} → {data.get('new_provider')}")

    async def _on_command_result(self, data: Dict[str, Any]):
        async with self._terminal_lock:
            success = data.get("success", True)
            message = data.get("message", "")
            if message:
                if success: await self.print_info(message)
                else: await self.print_error(message)

    # --- HELPER ---
    async def _flush_stream_buffer(self):
        # This is a helper and assumes the caller holds the terminal lock
        if self._stream_line_buffer:
            self.renderer.render_line(self._stream_line_buffer, is_thinking=self._in_thinking_block)
            self._stream_line_buffer = ""

    # --- LEGACY/COMPAT ---
    async def get_input(self) -> str:
        # Should not be called by agent anymore, but kept for Interface compliance
        return await self.input.read_input(is_main_loop=True) or ""

    async def confirm_tool_execution(self, tool_data: Dict[str, Any]) -> bool:
        # Deprecated
        return False

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