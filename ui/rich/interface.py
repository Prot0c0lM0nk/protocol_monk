"""
ui/rich/interface.py
The Rich UI Controller.
Updated for Full Event-Driven Architecture (Bidirectional).
"""

import asyncio
import sys
from typing import Dict, Any, List, Tuple

from ui.base import UI, ToolResult
from ui.prompts import AsyncPrompt
from agent.events import AgentEvents, get_event_bus
from .renderer import RichRenderer
from .input import RichInput
from .styles import console


class RichUI(UI):
    def __init__(self, event_bus=None):
        super().__init__()
        self.renderer = RichRenderer()
        self.input = RichInput()
        
        # FIX: Accept injected event_bus from main.py
        self._event_bus = event_bus or get_event_bus()
        
        # Stream buffer for handling updates during input
        self._stream_buffer = ""
        
        # State Management
        self.turn_complete = asyncio.Event()
        self.running = False
        
        self._setup_event_listeners()

    def _setup_event_listeners(self):
        # --- PASSIVE OUTPUT (Agent Speaking) ---
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

        # --- ACTIVE INPUT REQUESTS (Agent Asking) ---
        self._event_bus.subscribe(
            AgentEvents.INPUT_REQUESTED.value, self._on_input_requested
        )
        self._event_bus.subscribe(
            AgentEvents.TOOL_CONFIRMATION_REQUESTED.value, self._on_tool_confirmation_requested
        )

        # --- SYSTEM STATUS ---
        self._event_bus.subscribe(AgentEvents.ERROR.value, self._on_error)
        self._event_bus.subscribe(AgentEvents.WARNING.value, self._on_warning)
        self._event_bus.subscribe(AgentEvents.INFO.value, self._on_info)
        self._event_bus.subscribe(
            AgentEvents.COMMAND_RESULT.value, self._on_command_result
        )

        # --- LIFECYCLE ---
        self._event_bus.subscribe(
            AgentEvents.TASK_COMPLETE.value, self._on_task_complete
        )
        self._event_bus.subscribe(
            AgentEvents.MODEL_SWITCHED.value, self._on_model_switched
        )
        self._event_bus.subscribe(
            AgentEvents.PROVIDER_SWITCHED.value, self._on_provider_switched
        )

    # === MAIN LOOP ===
    
    async def run_loop(self):
        """
        The main UI lifecycle.
        1. Get User Input.
        2. Send to Agent.
        3. Wait for Agent to Finish (while handling intermediate events).
        """
        self.running = True
        # Ensure turn_complete is set initially so we can type the first message
        self.turn_complete.set()

        while self.running:
            try:
                # 1. Wait for user input
                user_input = await self.get_input()
                
                # FIX: Handle Ctrl+C (RichInput returns empty on interrupt, or we catch it)
                if user_input is None: # Explicit exit signal
                    break
                if not user_input and not self.running: # Shutdown signal received during input
                    break
                if not user_input:
                    continue
                
                # 2. Lock UI & Emit Input
                self.turn_complete.clear()
                await self._event_bus.emit(
                    AgentEvents.USER_INPUT.value, 
                    {"input": user_input}
                )

                # 3. Wait for Agent to finish thinking/acting
                # During this wait, active handlers (input_requested, tool_confirmation)
                # will be triggered by the event bus.
                await self.turn_complete.wait()
                
            except (KeyboardInterrupt, asyncio.CancelledError):
                print("\n[UI] Interrupted. Exiting...")
                self.running = False
                break
            except Exception as e:
                self.renderer.print_error(f"UI Loop Error: {e}")
                self.turn_complete.set() # Recovery

    # === ACTIVE LISTENERS (The Missing Link) ===

    async def _on_input_requested(self, data: Dict[str, Any]):
        """
        Agent needs nested input (e.g. Model Selection).
        We hijack the input stream momentarily.
        """
        prompt = data.get("prompt", "Value needed")
        
        # 1. Ask User
        user_value = await self.get_input(prompt_text=prompt)
        
        # 2. Respond to Agent
        await self._event_bus.emit(
            AgentEvents.INPUT_RESPONSE.value,
            {"input": user_value}
        )

    async def _on_tool_confirmation_requested(self, data: Dict[str, Any]):
        """
        Agent needs approval for a tool.
        """
        tool_call = data.get("tool_call", {})
        tool_call_id = data.get("tool_call_id")
        
        # 1. Ask User (using shared Prompt logic)
        approved = await self.confirm_tool_execution(tool_call)
        
        # 2. Respond to Agent
        await self._event_bus.emit(
            AgentEvents.TOOL_CONFIRMATION_RESPONSE.value,
            {
                "tool_call_id": tool_call_id,
                "approved": approved,
                "edits": None
            }
        )

    # === PASSIVE HANDLERS ===

    async def _on_stream_chunk(self, data: Dict[str, Any]):
        if self.renderer._is_locked:
            thinking = data.get("thinking")
            chunk = data.get("chunk", "")
            if thinking:
                self._stream_buffer += f"[THINKING]{thinking}"
            elif chunk:
                self._stream_buffer += chunk
            return

        thinking = data.get("thinking")
        if thinking:
            self.renderer.update_streaming(thinking, is_thinking=True)
            return

        chunk = data.get("chunk", "")
        if chunk:
            self.renderer.update_streaming(chunk, is_thinking=False)

    async def _on_response_complete(self, data: Dict[str, Any]):
        if self.renderer._is_locked:
            self._stream_buffer += "[COMPLETE]"
        else:
            self.renderer.end_streaming()
        
        # CRITICAL: Unlock the main loop
        self.turn_complete.set()

    async def _on_thinking_started(self, data: Dict[str, Any]):
        if self.renderer._is_locked:
            self._stream_buffer += "[THINKING_START]"
            return
        self.renderer.start_thinking(data.get("message", "Contemplating..."))

    async def _on_thinking_stopped(self, data: Dict[str, Any]):
        if self.renderer._is_locked:
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
            self._stream_buffer += f"[TOOL_RESULT]{name}|{res.success}|{res.output}"
            return
        self.renderer.render_tool_result(res, name)

    async def _on_error(self, data: Dict[str, Any]):
        if self.renderer._is_locked:
            self._stream_buffer += f"[ERROR]{data.get('message', 'Unknown Error')}"
            return
        self.renderer.print_error(data.get("message", "Unknown Error"))

    async def _on_warning(self, data: Dict[str, Any]):
        if self.renderer._is_locked:
            self._stream_buffer += f"[WARNING]{data.get('message', '')}"
            return
        self.renderer.print_system(f"[warning]Warning:[/] {data.get('message', '')}")

    async def _on_info(self, data: Dict[str, Any]):
        msg = data.get("message", "")
        context = data.get("context", "")
        items = data.get("data", [])

        # FIX: Check for Shutdown Signal
        if context == "shutdown":
            self.renderer.print_system(f"[bold]{msg}[/]")
            self.running = False
            self.turn_complete.set() # Unblock loop so it can exit
            return

        if self.renderer._is_locked:
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
        if not buffer:
            return []
        
        results = []
        i = 0
        current_content = ""
        
        while i < len(buffer):
            if buffer[i] == '[' and i < len(buffer) - 1:
                if current_content.strip():
                    results.append(("", current_content))
                    current_content = ""
                
                end = buffer.find(']', i)
                if end != -1:
                    marker = buffer[i+1:end]
                    content_start = end + 1
                    next_marker = buffer.find('[', content_start)
                    
                    if next_marker == -1:
                        marker_content = buffer[content_start:]
                        results.append((marker, marker_content))
                        break
                    else:
                        marker_content = buffer[content_start:next_marker]
                        results.append((marker, marker_content))
                        i = next_marker
                else:
                    current_content += buffer[i]
                    i += 1
            else:
                current_content += buffer[i]
                i += 1
        
        if current_content.strip():
            results.append(("", current_content))
        
        return results

    async def _flush_buffer(self):
        if not self._stream_buffer:
            return

        buffer = self._stream_buffer
        self._stream_buffer = ""

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
                pass
            elif marker == "TOOL_RESULT":
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
                # Check shutdown in buffer too
                if "context=shutdown" in content: # Simplified check
                    self.running = False
                    self.turn_complete.set()
                
                parts = content.split("|", 2)
                if len(parts) >= 1 and parts[0].strip():
                    self.renderer.print_system(parts[0].strip())
            elif marker == "COMMAND_RESULT":
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
                if thinking_active:
                    thinking_content += content
                else:
                    response_content += content

        if thinking_content or response_content:
            self.renderer.start_streaming()
            if thinking_content:
                self.renderer.update_streaming(thinking_content, is_thinking=True)
            if response_content:
                self.renderer.update_streaming(response_content, is_thinking=False)
            self.renderer.end_streaming()

    # --- BLOCKING INTERFACE ---
    async def get_input(self, prompt_text: str = "") -> str:
        self.renderer.lock_for_input()
        console.print()

        try:
            user_input = await self.input.get_input(prompt_text)
            return user_input
        finally:
            self.renderer.unlock_for_input()
            await self._flush_buffer()

    async def confirm_tool_execution(self, tool_data: Dict[str, Any]) -> bool:
        tool_name = tool_data.get("tool_name", "Unknown")
        if not tool_name and "action" in tool_data:
            tool_name = tool_data["action"]
            
        params = tool_data.get("parameters", {})

        self.renderer.render_tool_confirmation(tool_name, params)

        return await AsyncPrompt.confirm(
            "[monk.text]Execute this action?[/]", default=False, console=console
        )

    # --- VISUALS ---
    async def display_startup_banner(self, greeting: str):
        self.renderer.render_banner(greeting)

    async def display_selection_list(self, title: str, items: List[Any]):
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