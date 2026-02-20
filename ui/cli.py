"""CLI implementation using prompt_toolkit for Protocol Monk."""
import asyncio
import logging
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.shortcuts import radiolist_dialog
from prompt_toolkit.patch_stdout import patch_stdout

from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.agent.structs import UserRequest, ConfirmationResponse
from protocol_monk.config.settings import Settings
import time
import uuid

logger = logging.getLogger("PromptToolkitCLI")


class PromptToolkitCLI:
    """
    CLI implementation using prompt_toolkit.

    Features:
    - Stable single-line input for day-to-day usage
    - Tool confirmation dialogs
    - State symbols in prompt
    - Buffered responses shown per pass
    """

    def __init__(self, bus: EventBus, settings: Settings):
        self._bus = bus
        self._settings = settings
        self._running = False
        self._current_state = "idle"
        self._response_buffer = ""
        self._thinking_buffer = ""
        self._current_tool_call_id = None
        self._auto_confirm = bool(getattr(settings, "auto_confirm", False))
        self._verbose_ui = str(getattr(settings, "log_level", "INFO")).upper() == "DEBUG"

        # Status symbols
        self._status_symbols = {
            "idle": "idle",
            "thinking": "thinking...",
            "executing": "executing",
            "paused": "paused",
            "error": "error",
        }

        # Create prompt session with default bindings for reliable editing behavior.
        self._session = PromptSession(multiline=False)

    async def start(self) -> None:
        """Subscribe to all relevant events."""
        # Status events
        await self._bus.subscribe(
            EventTypes.STATUS_CHANGED, self._handle_status_changed
        )

        # Conversation events
        await self._bus.subscribe(
            EventTypes.STREAM_CHUNK, self._handle_stream_chunk
        )
        await self._bus.subscribe(
            EventTypes.RESPONSE_COMPLETE, self._handle_response_complete
        )

        # Tool events
        await self._bus.subscribe(
            EventTypes.TOOL_CONFIRMATION_REQUESTED,
            self._handle_tool_confirmation_requested,
        )
        await self._bus.subscribe(
            EventTypes.TOOL_EXECUTION_START, self._handle_tool_start
        )
        await self._bus.subscribe(
            EventTypes.TOOL_RESULT, self._handle_tool_result
        )
        await self._bus.subscribe(
            EventTypes.TOOL_EXECUTION_COMPLETE, self._handle_tool_complete
        )

        # System events
        await self._bus.subscribe(EventTypes.ERROR, self._handle_error)
        await self._bus.subscribe(EventTypes.WARNING, self._handle_warning)
        await self._bus.subscribe(EventTypes.INFO, self._handle_info)
        await self._bus.subscribe(
            EventTypes.AUTO_CONFIRM_CHANGED, self._handle_auto_confirm_changed
        )

        logger.info("PromptToolkitCLI started and listening")

    async def run(self) -> None:
        """Main REPL loop."""
        self._running = True

        print("\n" + "="*60)
        print("Protocol Monk CLI")
        print("Press Enter to submit")
        print("Type 'quit' or 'exit' to stop")
        print("="*60 + "\n")

        while self._running:
            # Block input until agent is idle
            if self._current_state != "idle":
                # Show status and wait briefly
                symbol = self._status_symbols.get(self._current_state, "?")
                await asyncio.sleep(0.1)
                continue

            try:
                # Get prompt with current state
                prompt = self._get_prompt()
                # Ensure background prints don't corrupt the current input buffer.
                with patch_stdout():
                    user_text = await self._session.prompt_async(prompt)

                # Handle exit commands
                if user_text.lower().strip() in ("quit", "exit", "q"):
                    print("Goodbye!")
                    self._running = False
                    break

                cmd = user_text.lower().strip()
                if cmd in ("/auto-approve", "/autoapprove", "/aa"):
                    await self._bus.emit(
                        EventTypes.SYSTEM_COMMAND_ISSUED,
                        {
                            "command": "toggle_auto_confirm",
                            "auto_confirm": not self._auto_confirm,
                        },
                    )
                    continue
                if cmd in ("/auto-approve on", "/autoapprove on", "/aa on"):
                    await self._bus.emit(
                        EventTypes.SYSTEM_COMMAND_ISSUED,
                        {"command": "toggle_auto_confirm", "auto_confirm": True},
                    )
                    continue
                if cmd in ("/auto-approve off", "/autoapprove off", "/aa off"):
                    await self._bus.emit(
                        EventTypes.SYSTEM_COMMAND_ISSUED,
                        {"command": "toggle_auto_confirm", "auto_confirm": False},
                    )
                    continue

                if user_text.strip():
                    # Emit user input
                    await self._emit_user_input(user_text)

            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                self._running = False
                break

    async def stop(self) -> None:
        """Stop the CLI."""
        self._running = False
        logger.info("PromptToolkitCLI stopped")

    def _get_prompt(self) -> str:
        """Get the current prompt with state symbol."""
        symbol = self._status_symbols.get(self._current_state, "?")
        return f"({symbol}) > "

    async def _emit_user_input(self, text: str) -> None:
        """Emit user input event."""
        request = UserRequest(
            text=text,
            source="cli",
            request_id=str(uuid.uuid4()),
            timestamp=time.time(),
        )
        await self._bus.emit(EventTypes.USER_INPUT_SUBMITTED, request)

    async def _emit_tool_confirmation(
        self, tool_call_id: str, decision: str
    ) -> None:
        """Emit tool confirmation response."""
        response = ConfirmationResponse(
            tool_call_id=tool_call_id,
            decision=decision,
            timestamp=time.time(),
        )
        await self._bus.emit(EventTypes.TOOL_CONFIRMATION_SUBMITTED, response)

    # Event Handlers

    async def _handle_status_changed(self, data: Any) -> None:
        """Handle STATUS_CHANGED events."""
        # Handle both AgentStatus dataclass and dict
        if hasattr(data, "status"):
            self._current_state = data.status
        else:
            self._current_state = data.get("status", "idle")

    async def _handle_stream_chunk(self, data: dict) -> None:
        """Handle STREAM_CHUNK events - buffer for later display."""
        chunk = data.get("chunk", "")
        channel = data.get("channel", "content")
        if not chunk:
            return
        if channel == "thinking":
            self._thinking_buffer += chunk
        else:
            self._response_buffer += chunk

    async def _handle_response_complete(self, data: dict) -> None:
        """Handle RESPONSE_COMPLETE - display model reasoning and response for this pass."""
        response_text = self._response_buffer.strip()
        thinking_text = self._thinking_buffer.strip()
        self._response_buffer = ""
        self._thinking_buffer = ""

        if not response_text:
            response_text = str(data.get("content", "")).strip()
        if not thinking_text:
            thinking_text = str(data.get("thinking", "")).strip()

        if thinking_text:
            print("\n[Reasoning]\n" + thinking_text + "\n")
        if response_text:
            print("\n" + response_text + "\n")

    async def _handle_tool_confirmation_requested(self, data: dict) -> None:
        """Handle TOOL_CONFIRMATION_REQUESTED using prompt_toolkit dialog."""
        tool_name = data.get("tool_name", "")
        parameters = data.get("parameters", {})
        tool_call_id = data.get("tool_call_id", "")

        self._current_tool_call_id = tool_call_id

        # Format parameters for display
        params_text = "\n".join(
            f"  {k}: {v}" for k, v in parameters.items()
        )

        # Show confirmation dialog
        result = await radiolist_dialog(
            title="Tool Execution",
            text=f"Execute tool: {tool_name}\n\nParameters:\n{params_text}",
            values=[
                ("approve", "Yes"),
                ("approve_auto", "Yes + Auto-Approve Edits"),
                ("reject", "No (Return Control)"),
            ],
        ).run_async()

        if result == "approve":
            await self._emit_tool_confirmation(tool_call_id, "approved")
        elif result == "approve_auto":
            await self._bus.emit(
                EventTypes.SYSTEM_COMMAND_ISSUED,
                {"command": "toggle_auto_confirm", "auto_confirm": True},
            )
            await self._emit_tool_confirmation(tool_call_id, "approved")
        elif result == "reject":
            await self._emit_tool_confirmation(tool_call_id, "rejected")

    async def _handle_tool_start(self, data: dict) -> None:
        """Handle TOOL_EXECUTION_START."""
        tool_name = data.get("tool_name", "")
        print(f"\n[Running: {tool_name}]")

    async def _handle_tool_result(self, data: dict) -> None:
        """Handle TOOL_RESULT."""
        success = data.get("success", False)
        output = data.get("output")
        if success and output:
            print(f"Output: {output}")

    async def _handle_tool_complete(self, data: dict) -> None:
        """Handle TOOL_EXECUTION_COMPLETE."""
        tool_name = data.get("tool_name", "")
        success = data.get("success", False)
        duration = data.get("duration", 0)
        icon = "" if success else ""
        print(f"{icon} {tool_name} completed ({duration:.2f}s)")

    async def _handle_error(self, data: dict) -> None:
        """Handle ERROR events."""
        message = data.get("message", str(data))
        print(f"[ERROR] {message}")

    async def _handle_warning(self, data: dict) -> None:
        """Handle WARNING events."""
        message = data.get("message", str(data))
        print(f"[WARNING] {message}")

    async def _handle_info(self, data: dict) -> None:
        """Handle INFO events."""
        if not self._verbose_ui:
            return
        message = data.get("message", str(data))
        print(f"[INFO] {message}")

    async def _handle_auto_confirm_changed(self, data: dict) -> None:
        """Track auto-confirm state updates."""
        self._auto_confirm = bool(data.get("auto_confirm", False))
