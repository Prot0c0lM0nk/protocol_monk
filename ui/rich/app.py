"""Primary Rich runtime UI for Protocol Monk."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from protocol_monk.agent.structs import ConfirmationResponse, UserRequest
from protocol_monk.config.settings import Settings
from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.ui.rich.input_handler import RichInputHandler
from protocol_monk.ui.rich.renderer import RichRenderer

logger = logging.getLogger("RichPromptToolkitUI")


class RichPromptToolkitUI:
    """
    Rich runtime UI backed by prompt-toolkit input.

    Behavior intentionally mirrors the CLI fallback for command and approval semantics.
    """

    def __init__(
        self,
        bus: EventBus,
        settings: Settings,
        *,
        renderer: RichRenderer | None = None,
        input_handler: RichInputHandler | None = None,
    ) -> None:
        self._bus = bus
        self._settings = settings
        self._renderer = renderer or RichRenderer()
        self._input_handler = input_handler or RichInputHandler()

        self._running = False
        self._current_state = "idle"
        self._pass_buffers: dict[str, dict[str, str]] = {}
        self._default_pass_id = "__legacy__"
        self._auto_confirm = bool(getattr(settings, "auto_confirm", False))
        self._verbose_ui = str(getattr(settings, "log_level", "INFO")).upper() == "DEBUG"
        self._confirmation_tasks: dict[str, asyncio.Task] = {}

        self._status_symbols = {
            "idle": "idle",
            "thinking": "thinking...",
            "executing": "executing",
            "paused": "paused",
            "error": "error",
        }

    async def start(self) -> None:
        await self._bus.subscribe(EventTypes.STATUS_CHANGED, self._handle_status_changed)
        await self._bus.subscribe(EventTypes.STREAM_CHUNK, self._handle_stream_chunk)
        await self._bus.subscribe(EventTypes.RESPONSE_COMPLETE, self._handle_response_complete)
        await self._bus.subscribe(
            EventTypes.TOOL_CONFIRMATION_REQUESTED,
            self._handle_tool_confirmation_requested,
        )
        await self._bus.subscribe(EventTypes.TOOL_EXECUTION_START, self._handle_tool_start)
        await self._bus.subscribe(EventTypes.TOOL_RESULT, self._handle_tool_result)
        await self._bus.subscribe(
            EventTypes.TOOL_EXECUTION_COMPLETE, self._handle_tool_complete
        )
        await self._bus.subscribe(EventTypes.ERROR, self._handle_error)
        await self._bus.subscribe(EventTypes.WARNING, self._handle_warning)
        await self._bus.subscribe(EventTypes.INFO, self._handle_info)
        await self._bus.subscribe(
            EventTypes.AUTO_CONFIRM_CHANGED,
            self._handle_auto_confirm_changed,
        )
        logger.info("RichPromptToolkitUI started and listening")

    async def run(self) -> None:
        self._running = True
        self._renderer.render_banner()

        while self._running:
            if self._current_state != "idle":
                await asyncio.sleep(0.1)
                continue

            prompt = self._get_prompt()
            try:
                self._renderer.lock_for_input()
                try:
                    user_text = await self._input_handler.prompt(prompt)
                finally:
                    self._renderer.unlock_for_input()
            except (EOFError, KeyboardInterrupt):
                self._renderer.render_info("Goodbye!")
                self._running = False
                break

            normalized = user_text.strip()
            if not normalized:
                continue

            if normalized.lower() in ("quit", "exit", "q"):
                self._renderer.render_info("Goodbye!")
                self._running = False
                break

            handled = await self._process_local_command(normalized)
            if handled:
                continue

            await self._emit_user_input(normalized)

    async def stop(self) -> None:
        self._running = False
        for task in list(self._confirmation_tasks.values()):
            task.cancel()
        self._confirmation_tasks.clear()
        self._renderer.shutdown()
        logger.info("RichPromptToolkitUI stopped")

    async def _process_local_command(self, text: str) -> bool:
        cmd = text.lower().strip()
        if cmd in ("/auto-approve", "/autoapprove", "/aa"):
            await self._bus.emit(
                EventTypes.SYSTEM_COMMAND_ISSUED,
                {
                    "command": "toggle_auto_confirm",
                    "auto_confirm": not self._auto_confirm,
                },
            )
            return True
        if cmd in ("/auto-approve on", "/autoapprove on", "/aa on"):
            await self._bus.emit(
                EventTypes.SYSTEM_COMMAND_ISSUED,
                {"command": "toggle_auto_confirm", "auto_confirm": True},
            )
            return True
        if cmd in ("/auto-approve off", "/autoapprove off", "/aa off"):
            await self._bus.emit(
                EventTypes.SYSTEM_COMMAND_ISSUED,
                {"command": "toggle_auto_confirm", "auto_confirm": False},
            )
            return True
        return False

    def _get_prompt(self) -> str:
        symbol = self._status_symbols.get(self._current_state, "?")
        return f"({symbol}) > "

    async def _emit_user_input(self, text: str) -> None:
        request = UserRequest(
            text=text,
            source="rich",
            request_id=str(uuid.uuid4()),
            timestamp=time.time(),
        )
        await self._bus.emit(EventTypes.USER_INPUT_SUBMITTED, request)

    async def _emit_tool_confirmation(self, tool_call_id: str, decision: str) -> None:
        response = ConfirmationResponse(
            tool_call_id=tool_call_id,
            decision=decision,
            timestamp=time.time(),
        )
        await self._bus.emit(EventTypes.TOOL_CONFIRMATION_SUBMITTED, response)

    async def _handle_status_changed(self, data: Any) -> None:
        if hasattr(data, "status"):
            status = str(getattr(data, "status", "idle"))
            message = str(getattr(data, "message", "") or "")
        else:
            status = str(data.get("status", "idle"))
            message = str(data.get("message", "") or "")
        self._current_state = status
        self._renderer.render_status(status, message)

    async def _handle_stream_chunk(self, data: dict) -> None:
        chunk = data.get("chunk", "")
        channel = data.get("channel", "content")
        if not chunk:
            return
        pass_id = self._normalize_pass_id(data.get("pass_id"))
        buffer = self._pass_buffers.setdefault(pass_id, {"content": "", "thinking": ""})
        if channel == "thinking":
            buffer["thinking"] += chunk
        else:
            buffer["content"] += chunk
        self._renderer.update_stream(
            thinking=buffer.get("thinking", ""),
            content=buffer.get("content", ""),
        )

    async def _handle_response_complete(self, data: dict) -> None:
        pass_id = self._normalize_pass_id(data.get("pass_id"))
        buffer = self._pass_buffers.pop(pass_id, {"content": "", "thinking": ""})
        response_text = str(buffer.get("content", "")).strip()
        thinking_text = str(buffer.get("thinking", "")).strip()

        if not response_text:
            response_text = str(data.get("content", "")).strip()
        if not thinking_text:
            thinking_text = str(data.get("thinking", "")).strip()

        self._renderer.finalize_response(
            thinking=thinking_text,
            content=response_text,
            empty_marker=not response_text and not thinking_text,
        )

    async def _handle_tool_confirmation_requested(self, data: dict) -> None:
        tool_name = data.get("tool_name", "")
        parameters = data.get("parameters", {})
        tool_call_id = data.get("tool_call_id", "")

        task = asyncio.create_task(
            self._run_confirmation_dialog(tool_name, parameters, tool_call_id)
        )
        self._confirmation_tasks[tool_call_id] = task

        def _cleanup(_: asyncio.Task, call_id: str = tool_call_id) -> None:
            self._confirmation_tasks.pop(call_id, None)

        task.add_done_callback(_cleanup)

    async def _run_confirmation_dialog(
        self,
        tool_name: str,
        parameters: dict,
        tool_call_id: str,
    ) -> None:
        self._renderer.render_tool_confirmation(tool_name, parameters)
        self._renderer.lock_for_input()
        try:
            result = await self._input_handler.confirm_tool_execution(
                tool_name=tool_name,
                parameters=parameters,
            )
        finally:
            self._renderer.unlock_for_input()

        if result == "approve":
            await self._emit_tool_confirmation(tool_call_id, "approved")
            return
        if result == "approve_auto":
            await self._bus.emit(
                EventTypes.SYSTEM_COMMAND_ISSUED,
                {"command": "toggle_auto_confirm", "auto_confirm": True},
            )
            await self._emit_tool_confirmation(tool_call_id, "approved")
            return

        # Deterministic fallback: closed dialog, timeout fallback failure, or invalid token.
        await self._emit_tool_confirmation(tool_call_id, "rejected")

    async def _handle_tool_start(self, data: dict) -> None:
        tool_name = data.get("tool_name", "")
        self._renderer.render_tool_start(tool_name)

    async def _handle_tool_result(self, data: dict) -> None:
        self._renderer.render_tool_result(
            success=bool(data.get("success", False)),
            output=data.get("output"),
            error=data.get("error"),
        )

    async def _handle_tool_complete(self, data: dict) -> None:
        self._renderer.render_tool_complete(
            tool_name=data.get("tool_name", ""),
            success=bool(data.get("success", False)),
            duration=float(data.get("duration", 0.0)),
        )

    async def _handle_error(self, data: dict) -> None:
        message = data.get("message", str(data))
        self._renderer.render_error(message, recovered=bool(data.get("recovered", False)))

    async def _handle_warning(self, data: dict) -> None:
        message = data.get("message", str(data))
        self._renderer.render_warning(message)

    async def _handle_info(self, data: dict) -> None:
        if not self._verbose_ui:
            return
        message = data.get("message", str(data))
        self._renderer.render_info(message)

    async def _handle_auto_confirm_changed(self, data: dict) -> None:
        self._auto_confirm = bool(data.get("auto_confirm", False))
        state = "enabled" if self._auto_confirm else "disabled"
        self._renderer.render_info(f"Auto-confirm {state}")

    def _normalize_pass_id(self, pass_id: Any) -> str:
        text = str(pass_id).strip() if pass_id is not None else ""
        return text or self._default_pass_id
