import asyncio
from typing import Dict, Any, Optional

from ui.base import UI, ToolResult
from ui.plain.renderer import PlainRenderer
from ui.async_input_interface import AsyncInputManager
from ui.async_keyboard_capture import create_keyboard_capture
from ui.async_prompts import create_async_prompts
from agent.events import AgentEvents, EventBus

class PlainInterface(UI):
    """
    A lightweight, asynchronous CLI interface.
    """
    def __init__(self, event_bus: Optional[EventBus] = None, **kwargs):
        super().__init__()
        
        # 1. Setup Async Input System
        self.input_manager = AsyncInputManager()
        self.capture = create_keyboard_capture()
        self.input_manager.register_capture("keyboard", self.capture)
        self.prompts = create_async_prompts(self.input_manager)

        # Alias for main.py (so it can call ui.input.start_capture())
        self.input = self.capture 

        self.renderer = PlainRenderer()
        self.event_bus = event_bus
        
        # Synchronization: Controls when the user is allowed to type
        # We start 'set' so the first prompt appears immediately.
        self._turn_complete = asyncio.Event()
        self._turn_complete.set()

        if self.event_bus:
            self._subscribe_to_events()
        else:
            self.renderer.print_warning("UI initialized without Event Bus.")

    def _subscribe_to_events(self):
        """
        Synchronous subscription to events.
        (Removed 'async' to fix RuntimeWarning in __init__)
        """
        # Streaming & Content
        self.event_bus.subscribe(AgentEvents.STREAM_CHUNK.value, self._on_stream_chunk)
        self.event_bus.subscribe(AgentEvents.RESPONSE_COMPLETE.value, self._on_response_complete)
        
        # Tool Lifecycle
        self.event_bus.subscribe(AgentEvents.TOOL_EXECUTION_START.value, self._on_tool_start)
        self.event_bus.subscribe(AgentEvents.TOOL_RESULT.value, self._on_tool_result)
        self.event_bus.subscribe(AgentEvents.TOOL_ERROR.value, self._on_tool_error)
        
        # System
        self.event_bus.subscribe(AgentEvents.INFO.value, self._on_info)
        self.event_bus.subscribe(AgentEvents.ERROR.value, self._on_error)
        self.event_bus.subscribe(AgentEvents.WARNING.value, self._on_warning)

    # --- The Main Loop (Missing in previous version) ---

    async def run_loop(self):
        """
        The main driver loop called by main.py.
        It coordinates waiting for the agent and prompting the user.
        """
        # Small sleep to let startup banners finish printing
        await asyncio.sleep(0.1)

        while True:
            try:
                # 1. Wait for the Agent to finish its turn
                await self._turn_complete.wait()

                # 2. Get User Input
                user_text = await self.get_input()
                
                # Handle empty input or exit commands locally
                if not user_text.strip():
                    continue
                
                if user_text.lower() in ('/exit', '/quit'):
                    self.renderer.print_system("Exiting...")
                    break

                # 3. Lock the turn (Agent is about to think)
                self._turn_complete.clear()

                # 4. Dispatch to Agent Service
                await self.event_bus.emit(AgentEvents.USER_INPUT.value, {"input": user_text})

            except asyncio.CancelledError:
                self.renderer.print_system("Loop cancelled.")
                break
            except Exception as e:
                self.renderer.print_error(f"UI Loop Error: {e}")
                # Don't infinite loop on error; pause briefly and reset
                await asyncio.sleep(1)
                self._turn_complete.set()

    # --- Event Handlers ---

    async def _on_stream_chunk(self, data: Dict[str, Any]):
        content = data.get("content") or data.get("chunk") or ""
        if content:
            self.renderer.stream(content)

    async def _on_response_complete(self, data: Dict[str, Any]):
        """Signal that the agent is done and we can prompt again."""
        self.renderer.new_line()
        self._turn_complete.set()

    async def _on_tool_start(self, data: Dict[str, Any]):
        tool_name = data.get("tool_name", "Unknown Tool")
        params = data.get("arguments") or data.get("input") or {}
        self.renderer.print_tool_call(tool_name, params)

    async def _on_tool_result(self, data: Dict[str, Any]):
        tool_name = data.get("tool_name", "Tool")
        output = data.get("output", "")
        self.renderer.print_tool_result(tool_name, str(output))

    async def _on_tool_error(self, data: Dict[str, Any]):
        error_msg = data.get("error") or "Unknown tool error"
        self.renderer.print_error(f"Tool Failure: {error_msg}")

    async def _on_info(self, data: Dict[str, Any]):
        msg = data.get("message", "")
        if msg:
            self.renderer.print_system(msg)

    async def _on_error(self, data: Dict[str, Any]):
        msg = data.get("message") or str(data)
        self.renderer.print_error(msg)
        
    async def _on_warning(self, data: Dict[str, Any]):
        msg = data.get("message") or str(data)
        self.renderer.print_warning(msg)

    # --- Interaction Methods ---
    
    async def get_input(self) -> str:
        self.renderer.new_line()
        # Ensure capture is active
        await self.input_manager.start_capture("keyboard")
        return await self.prompts.text("\n>>> ")

    async def confirm_tool_execution(self, tool_call_data: Dict[str, Any]) -> bool:
        self.renderer.new_line()
        tool_name = tool_call_data.get("name", "Unknown Tool")
        args = tool_call_data.get("arguments", {})
        
        self.renderer.print_tool_call(tool_name, args)
        
        await self.input_manager.start_capture("keyboard")
        return await self.prompts.confirm(f"Execute {tool_name}?")

    # --- Base Class Implementation (Output) ---

    async def print_stream(self, text: str):
        self.renderer.stream(text)

    async def print_error(self, message: str):
        self.renderer.print_error(message)

    async def print_info(self, message: str):
        self.renderer.print_system(message)
    
    async def print_warning(self, message: str):
        self.renderer.print_warning(message)

    async def start_thinking(self):
        self.renderer.print_system("Thinking...")

    async def stop_thinking(self):
        pass

    async def display_tool_result(self, result: ToolResult, tool_name: str):
        self.renderer.print_tool_result(tool_name, result.output)

    async def display_startup_banner(self, greeting: str):
        print("\n" + "="*40)
        print(f" {greeting}")
        print("="*40 + "\n")

    async def shutdown(self):
        self.renderer.print_system("Shutting down interface...")
        await self.input_manager.stop_all_captures()