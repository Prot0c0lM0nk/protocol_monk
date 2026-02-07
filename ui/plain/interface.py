"""
PlainInterface - Development UI establishing patterns for RichUI/TextualUI.
"""

import asyncio
from typing import Optional, Dict, Any

from ui.base import UI, ToolResult
from ui.plain.renderer import PlainRenderer
from ui.plain.input_handler import InputHandler
from agent.events import EventBus, AgentEvents


class _InputAdapter:
    """
    Adapter for backward compatibility with main.py.
    With prompt_toolkit, we don't need separate capture - it's all handled internally.
    """

    def __init__(self, input_handler: InputHandler):
        self._input_handler = input_handler

    async def start_capture(self):
        """No-op for prompt_toolkit - input is handled in get_input()"""
        pass

    async def stop_capture(self):
        """No-op for prompt_toolkit - sessions clean up automatically"""
        pass


class PlainInterface(UI):
    """
    Plain CLI interface using prompt_toolkit for async input.

    Turn Coordination:
    - User can type ">>>" only when _turn_complete is set
    - Agent clears the flag when processing
    - Agent sets the flag via RESPONSE_COMPLETE when done

    Shutdown:
    - Ctrl+D (EOF) triggers graceful shutdown
    """

    def __init__(self, event_bus: Optional[EventBus] = None, **kwargs):
        super().__init__()

        # Input & Output
        self.input_handler = InputHandler()
        self.renderer = PlainRenderer()
        self.event_bus = event_bus

        # Alias for main.py compatibility
        # With prompt_toolkit, we don't need separate capture - it's all handled internally
        self.input = _InputAdapter(self.input_handler)

        # Turn coordination: Controls when user can type
        # Start 'set' so first prompt appears immediately
        self._turn_complete = asyncio.Event()
        self._turn_complete.set()

        # Track last user input for error recovery resend
        self._last_user_input: Optional[str] = None

        if self.event_bus:
            self._subscribe_to_events()
        else:
            self.renderer.print_warning("UI initialized without Event Bus.")

    def _subscribe_to_events(self):
        """Subscribe to all agent events."""
        # Streaming & Content
        self.event_bus.subscribe(AgentEvents.STREAM_CHUNK.value, self._on_stream_chunk)
        self.event_bus.subscribe(
            AgentEvents.RESPONSE_COMPLETE.value, self._on_response_complete
        )

        # Tool Lifecycle
        self.event_bus.subscribe(
            AgentEvents.TOOL_CONFIRMATION_REQUESTED.value,
            self._on_tool_confirmation_request,
        )
        self.event_bus.subscribe(
            AgentEvents.TOOL_EXECUTION_START.value, self._on_tool_start
        )
        self.event_bus.subscribe(AgentEvents.TOOL_RESULT.value, self._on_tool_result)
        self.event_bus.subscribe(AgentEvents.TOOL_ERROR.value, self._on_tool_error)

        # Command/Input Events (for slash commands that prompt user)
        self.event_bus.subscribe(
            AgentEvents.INPUT_REQUESTED.value, self._on_input_requested
        )

        # System
        self.event_bus.subscribe(AgentEvents.INFO.value, self._on_info)
        self.event_bus.subscribe(AgentEvents.ERROR.value, self._on_error)
        self.event_bus.subscribe(AgentEvents.WARNING.value, self._on_warning)
        self.event_bus.subscribe(AgentEvents.APP_STARTED.value, self._on_app_started)

    # ========================================
    # Main Loop
    # ========================================

    async def run_loop(self):
        """
        The main driver loop called by main.py.
        Coordinates user input and agent processing.
        """
        # Small sleep to let startup banners finish
        await asyncio.sleep(0.1)

        while True:
            try:
                # 1. Wait for agent to finish its turn (unblocks on RESPONSE_COMPLETE)
                await self._turn_complete.wait()

                # 2. Get user input (blocking via prompt_toolkit)
                user_text = await self.get_input()

                # Handle empty/cancelled input (Ctrl+D returns None)
                if user_text is None:
                    # Ctrl+D pressed, signal shutdown
                    self.renderer.print_system("Shutting down...")
                    break

                # Handle empty input (just Enter)
                if not user_text.strip():
                    continue

                # Handle exit command
                if user_text.lower() in ("/exit", "/quit"):
                    # Command dispatcher handles /quit specially
                    self.renderer.print_system("Exiting...")
                    break

                # 3. Store for potential error recovery
                self._last_user_input = user_text

                # 4. Lock the turn (agent is about to think)
                self._turn_complete.clear()

                # 5. Dispatch to AgentService
                await self.event_bus.emit(
                    AgentEvents.USER_INPUT.value, {"input": user_text}
                )

            except asyncio.CancelledError:
                self.renderer.print_system("Loop cancelled.")
                break
            except Exception as e:
                self.renderer.print_error(f"UI Loop Error: {e}")
                await asyncio.sleep(1)
                self._turn_complete.set()

    # ========================================
    # Event Handlers
    # ========================================

    async def _on_stream_chunk(self, data: Dict[str, Any]):
        """Stream model output character by character."""
        content = data.get("content") or data.get("chunk") or ""
        if content:
            self.renderer.stream(content)

    async def _on_response_complete(self, data: Dict[str, Any]):
        """
        Agent is done processing. Unlock the UI for user input.
        This is what triggers the ">>>" prompt to appear.
        """
        self.renderer.new_line()
        self._turn_complete.set()

    async def _on_tool_confirmation_request(self, data: Dict[str, Any]):
        """
        Agent is requesting tool confirmation.
        Block here, get user input, emit response.
        """
        tool_call = data.get("tool_call", {})
        tool_call_id = data.get("tool_call_id", "")
        action = tool_call.get("action", "Unknown")

        # Display the tool request
        params = tool_call.get("parameters", {})
        self.renderer.new_line()
        param_str = str(params)
        if len(param_str) > 150:
            param_str = param_str[:147] + "..."
        print(f"[MONK] Tool Request: {action}({param_str})")
        self._maybe_print_long_running_hint(action, params)

        # Block for user confirmation
        approved = await self.input_handler.confirm("Execute this tool?", default=False)

        # Emit response
        await self.event_bus.emit(
            AgentEvents.TOOL_CONFIRMATION_RESPONSE.value,
            {
                "tool_call_id": tool_call_id,
                "approved": approved,
                "edits": None,  # Could add editing later
            },
        )

    def _maybe_print_long_running_hint(self, action: str, params: Dict[str, Any]):
        if action != "execute_command":
            return
        command = str(params.get("command", "")).lower()
        long_running_markers = [
            "npm run dev",
            "pnpm dev",
            "yarn dev",
            "vite",
            "next dev",
            "serve",
            "dev server",
            "tail -f",
        ]
        if any(marker in command for marker in long_running_markers):
            self.renderer.print_warning(
                "If input appears stuck, press Ctrl+C to return to the prompt. "
                "The server/process will keep running."
            )

    async def _on_tool_start(self, data: Dict[str, Any]):
        """Tool execution starting."""
        count = data.get("count", 1)
        tools = data.get("tools", [])
        self.renderer.new_line()
        self.renderer.print_system(f"Executing {count} tool(s): {', '.join(tools)}")

    async def _on_tool_result(self, data: Dict[str, Any]):
        """Tool execution complete, display result."""
        result = data.get("result")
        tool_name = data.get("tool_name", "Tool")
        if result:
            self.renderer.print_tool_result(tool_name, str(result.output))

    async def _on_tool_error(self, data: Dict[str, Any]):
        """Tool execution failed."""
        error_msg = data.get("error") or "Unknown tool error"
        self.renderer.print_error(f"Tool Failure: {error_msg}")

    async def _on_input_requested(self, data: Dict[str, Any]):
        """
        Command dispatcher needs user input (e.g., for /file, /model).
        Block for input, emit response.
        """
        prompt_text = data.get("prompt", "Enter value: ")
        response = await self.input_handler.get_input(prompt_text)
        await self.event_bus.emit(
            AgentEvents.INPUT_RESPONSE.value, {"input": response or ""}
        )

    async def _on_info(self, data: Dict[str, Any]):
        """System/info message."""
        msg = data.get("message", "")
        items = data.get("data", [])
        context = data.get("context", "")

        if msg:
            if context in ["model_selection", "provider_selection"] and items:
                await self.display_selection_list(msg, items)
            else:
                self.renderer.print_system(msg)

    async def _on_error(self, data: Dict[str, Any]):
        """
        Agent error - show error and offer recovery options.
        User can choose: Resend to model OR Return control to user.
        """
        msg = data.get("message") or str(data)
        self.renderer.print_error(msg)

        # Offer recovery options
        recovery_index = await self.input_handler.select_with_arrows(
            "Agent Error - Choose an action:",
            ["Resend to model", "Return control to user"],
            default_index=1,  # Default to returning control
        )

        if recovery_index == 0:
            # Resend last input to agent
            if self._last_user_input:
                self._turn_complete.clear()
                await self.event_bus.emit(
                    AgentEvents.USER_INPUT.value, {"input": self._last_user_input}
                )
        else:
            # Return control to user - unlock turn
            self._turn_complete.set()

    async def _on_warning(self, data: Dict[str, Any]):
        """Warning message."""
        msg = data.get("message") or str(data)
        self.renderer.print_warning(msg)

    async def _on_app_started(self, data: Dict[str, Any]):
        """App started, display welcome banner."""
        model = data.get("model", "Unknown")
        provider = data.get("provider", "Unknown")
        working_dir = data.get("working_dir", ".")

        banner = f"""
╔═════════════════════════════════════════════════════════╗
║         Protocol Monk - Plain Interface                 ║
╠═════════════════════════════════════════════════════════╣
║  Model:    {model:<38} ║
║  Provider: {provider:<38} ║
║  Working:  {working_dir:<38} ║
╠═════════════════════════════════════════════════════════╣
║  Type /help for commands                                ║
║  Ctrl+D to exit                                         ║
╚═════════════════════════════════════════════════════════╝
"""
        print(banner)

    # ========================================
    # Base Class Methods
    # ========================================

    async def get_input(self) -> str:
        """Get input from user (blocking)."""
        return await self.input_handler.get_input(">>> ")

    async def confirm_tool_execution(self, tool_call_data: Dict[str, Any]) -> bool:
        """
        Legacy method - now handled via TOOL_CONFIRMATION_REQUESTED event.
        Kept for base class compatibility.
        """
        tool_name = tool_call_data.get("name", "Unknown Tool")
        return await self.input_handler.confirm(f"Execute {tool_name}?", default=False)

    async def print_stream(self, text: str):
        self.renderer.stream(text)

    async def print_error(self, message: str):
        self.renderer.print_error(message)

    async def print_info(self, message: str):
        self.renderer.print_system(message)

    async def print_warning(self, message: str):
        self.renderer.print_warning(message)

    async def start_thinking(self):
        """Show thinking indicator (static print for PlainUI)."""
        self.renderer.print_system("[MONK] Thinking...")

    async def stop_thinking(self):
        """Clear thinking indicator."""
        pass

    async def display_tool_result(self, result: ToolResult, tool_name: str):
        self.renderer.print_tool_result(tool_name, result.output)

    async def display_startup_banner(self, greeting: str):
        # Banner handled via APP_STARTED event
        pass

    async def display_selection_list(self, title: str, items):
        """Display selection list for model/provider switching."""
        self.renderer.render_selection_list(title, items)

    async def shutdown(self):
        """Shutdown gracefully."""
        self.renderer.print_system("Shutting down interface...")
        # prompt_toolkit sessions handle cleanup automatically
