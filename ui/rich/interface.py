"""
ui/rich/interface.py
The Rich UI Controller.
"""

import asyncio
from typing import Dict, Any, List, Tuple

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
        # Stream buffer for handling updates during input
        self._stream_buffer = ""
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
        # Check if renderer is locked (waiting for input)
        if self.renderer._is_locked:
            # Buffer the stream chunk for later
            thinking = data.get("thinking")
            chunk = data.get("chunk", "")
            if thinking:
                self._stream_buffer += f"[THINKING]{thinking}"
            elif chunk:
                self._stream_buffer += chunk
            return

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
        if self.renderer._is_locked:
            # Mark buffer as complete for later flushing
            self._stream_buffer += "[COMPLETE]"
            return
        self.renderer.end_streaming()

    async def _on_thinking_started(self, data: Dict[str, Any]):
        if self.renderer._is_locked:
            # Buffer thinking state change
            self._stream_buffer += "[THINKING_START]"
            return
        self.renderer.start_thinking(data.get("message", "Contemplating..."))

    async def _on_thinking_stopped(self, data: Dict[str, Any]):
        if self.renderer._is_locked:
            # Buffer thinking state change
            self._stream_buffer += "[THINKING_STOP]"
            return
        self.renderer.stop_thinking()

    async def _on_tool_result(self, data: Dict[str, Any]):
        res = data.get("result")
        name = data.get("tool_name", "Unknown")
        if not hasattr(res, "success"):
            from ui.base import ToolResult

            res = ToolResult(success=True, output=str(res), tool_name=name)
        
        if self.renderer._is_locked:
            # Buffer tool result for later rendering
            self._stream_buffer += f"[TOOL_RESULT]{name}|{res.success}|{res.output}"
            return
        self.renderer.render_tool_result(res, name)

    async def _on_error(self, data: Dict[str, Any]):
        if self.renderer._is_locked:
            # Buffer error message
            self._stream_buffer += f"[ERROR]{data.get('message', 'Unknown Error')}"
            return
        self.renderer.print_error(data.get("message", "Unknown Error"))

    async def _on_warning(self, data: Dict[str, Any]):
        if self.renderer._is_locked:
            # Buffer warning message
            self._stream_buffer += f"[WARNING]{data.get('message', '')}"
            return
        self.renderer.print_system(f"[warning]Warning:[/] {data.get('message', '')}")

    async def _on_info(self, data: Dict[str, Any]):
        msg = data.get("message", "")
        context = data.get("context", "")
        items = data.get("data", [])

        if self.renderer._is_locked:
            # Buffer info message
            self._stream_buffer += f"[INFO]{msg}|{context}|{len(items) if items else 0}"
            return

        if context in ["model_selection", "provider_selection"] and items:
            await self.display_selection_list(msg, items)
        elif msg.strip():
            self.renderer.print_system(msg)

    async def _on_command_result(self, data: Dict[str, Any]):
        success = data.get("success", True)
        message = data.get("message", "")
        
        if self.renderer._is_locked:
            # Buffer command result
            self._stream_buffer += f"[COMMAND_RESULT]{success}|{message}"
            return
            
        if message:
            self.renderer.render_command_result(success, message)

    async def _on_task_complete(self, data: Dict[str, Any]):
        if self.renderer._is_locked:
            self._stream_buffer += "[TASK_COMPLETE]"
            return
        self.renderer.end_streaming()

    async def _on_model_switched(self, data: Dict[str, Any]):
        if self.renderer._is_locked:
            self._stream_buffer += f"[MODEL_SWITCHED]{data.get('new_model')}"
            return
        self.renderer.print_system(f"Model Switched: {data.get('new_model')}")

    async def _on_provider_switched(self, data: Dict[str, Any]):
        if self.renderer._is_locked:
            self._stream_buffer += f"[PROVIDER_SWITCHED]{data.get('new_provider')}"
            return
        self.renderer.print_system(f"Provider Switched: {data.get('new_provider')}")

    # --- BUFFER FLUSHING ---
    def _parse_buffer_content(self, buffer: str) -> List[Tuple[str, str]]:
        """
        Parse buffer content, extracting both plain text and marked content.
        
        This replaces the broken regex that missed plain content at the start.
        """
        if not buffer:
            return []
        
        results = []
        i = 0
        current_content = ""
        
        while i < len(buffer):
            if buffer[i] == '[' and i < len(buffer) - 1:
                # Found potential marker start
                # First, save any accumulated plain content
                if current_content.strip():
                    results.append(("", current_content))
                    current_content = ""
                
                # Find the closing bracket
                end = buffer.find(']', i)
                if end != -1:
                    marker = buffer[i+1:end]
                    
                    # Find content until next marker or end
                    content_start = end + 1
                    next_marker = buffer.find('[', content_start)
                    
                    if next_marker == -1:
                        # No more markers, take rest of string
                        marker_content = buffer[content_start:]
                        results.append((marker, marker_content))
                        break
                    else:
                        # Take content until next marker
                        marker_content = buffer[content_start:next_marker]
                        results.append((marker, marker_content))
                        i = next_marker
                else:
                    # No closing bracket, treat as plain text
                    current_content += buffer[i]
                    i += 1
            else:
                current_content += buffer[i]
                i += 1
        
        # Don't forget final plain content
        if current_content.strip():
            results.append(("", current_content))
        
        return results
    async def _flush_buffer(self):
        """Process and render all buffered events after input completes."""
        if not self._stream_buffer:
            return

        # Parse and process buffered commands
        buffer = self._stream_buffer
        self._stream_buffer = ""

        # Parse the buffer for special markers
        # Use the new parser instead of broken regex
        matches = self._parse_buffer_content(buffer)

        thinking_active = False
        thinking_content = ""
        response_content = ""

        for marker, content in matches:
            marker = marker.strip()
            content = content.strip()

            if marker == "THINKING":
                thinking_content += content
                thinking_active = True
            elif marker == "THINKING_START":
                thinking_active = True
            elif marker == "THINKING_STOP":
                thinking_active = False
            elif marker == "COMPLETE":
                # End of streaming
                pass
            elif marker == "TOOL_RESULT":
                # Parse: name|success|output
                parts = content.split("|", 2)
                if len(parts) == 3:
                    name, success, output = parts
                    from ui.base import ToolResult
                    res = ToolResult(success=success.lower() == "true", output=output, tool_name=name)
                    self.renderer.render_tool_result(res, name)
            elif marker == "ERROR":
                self.renderer.print_error(content)
            elif marker == "WARNING":
                self.renderer.print_system(f"[warning]Warning:[/] {content}")
            elif marker == "INFO":
                # Parse: msg|context|item_count
                parts = content.split("|", 2)
                if len(parts) >= 1 and parts[0].strip():
                    self.renderer.print_system(parts[0].strip())
            elif marker == "COMMAND_RESULT":
                # Parse: success|message
                parts = content.split("|", 1)
                if len(parts) == 2:
                    success, message = parts
                    if message.strip():
                        self.renderer.render_command_result(success.lower() == "true", message)
            elif marker == "TASK_COMPLETE":
                self.renderer.end_streaming()
            elif marker == "MODEL_SWITCHED":
                self.renderer.print_system(f"Model Switched: {content}")
            elif marker == "PROVIDER_SWITCHED":
                self.renderer.print_system(f"Provider Switched: {content}")
            elif marker == "" and content:
                # Plain content (stream chunks)
                if thinking_active:
                    thinking_content += content
                else:
                    response_content += content

        # Render any buffered streaming content
        if thinking_content or response_content:
            # Start streaming if we have content
            self.renderer.start_streaming()

            if thinking_content:
                self.renderer.update_streaming(thinking_content, is_thinking=True)
            if response_content:
                self.renderer.update_streaming(response_content, is_thinking=False)

            # End streaming to finalize
            self.renderer.end_streaming()

    # --- BLOCKING INTERFACE ---
    async def get_input(self) -> str:
        # 1. Lock the renderer immediately. 
        # This stops any lingering stream chunks from hijacking the terminal.
        self.renderer.lock_for_input()
        
        # 2. Print a newline to separate the previous stream from the prompt
        console.print()

        # 3. Get Input
        try:
            user_input = await self.input.get_input("User Input")
            return user_input
        finally:
            # 4. Always unlock, even if KeyboardInterrupt occurs
            self.renderer.unlock_for_input()
            # 5. Flush any buffered events that occurred during input
            await self._flush_buffer()

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