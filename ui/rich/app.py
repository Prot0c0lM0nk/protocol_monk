"""Primary Rich runtime UI for Protocol Monk."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import asdict
from dataclasses import dataclass
from typing import Any

from protocol_monk.agent.structs import ConfirmationResponse, UserRequest
from protocol_monk.config.settings import Settings
from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.ui.rich.input_handler import RichInputHandler
from protocol_monk.ui.rich.renderer import RichRenderer

logger = logging.getLogger("RichPromptToolkitUI")


@dataclass
class HeaderState:
    provider: str
    model: str
    state: str
    state_message: str
    auto_confirm: bool
    total_tokens: int
    context_limit: int
    message_count: int
    loaded_files_count: int

    def as_renderer_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("state_message", None)
        return payload


@dataclass
class ToolOutputRecord:
    tool_name: str
    success: bool
    output_text: str
    output_lines: int
    output_chars: int


class RichPromptToolkitUI:
    """
    Rich runtime UI backed by prompt-toolkit input.

    Behavior intentionally mirrors the CLI fallback for command and approval semantics.
    """

    LARGE_OUTPUT_CHAR_THRESHOLD = 160
    LARGE_OUTPUT_LINE_THRESHOLD = 6
    FULL_OUTPUT_SOFT_CAP = 20_000
    TOOL_OUTPUT_QUEUE_MAX = 10

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
        self._pending_tool_outputs: deque[ToolOutputRecord] = deque()
        self._tool_progress_seen: dict[str, tuple[Any, str]] = {}
        self._header = HeaderState(
            provider=str(getattr(settings, "llm_provider", "") or ""),
            model=str(getattr(settings, "active_model_name", "") or ""),
            state="idle",
            state_message="",
            auto_confirm=self._auto_confirm,
            total_tokens=0,
            context_limit=int(getattr(settings, "context_window_limit", 0) or 0),
            message_count=0,
            loaded_files_count=0,
        )

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
        await self._bus.subscribe(
            EventTypes.TOOL_EXECUTION_PROGRESS, self._handle_tool_progress
        )
        await self._bus.subscribe(EventTypes.ERROR, self._handle_error)
        await self._bus.subscribe(EventTypes.WARNING, self._handle_warning)
        await self._bus.subscribe(EventTypes.INFO, self._handle_info)
        await self._bus.subscribe(
            EventTypes.AUTO_CONFIRM_CHANGED,
            self._handle_auto_confirm_changed,
        )
        await self._bus.subscribe(EventTypes.MODEL_SWITCHED, self._handle_model_switched)
        await self._bus.subscribe(
            EventTypes.PROVIDER_SWITCHED,
            self._handle_provider_switched,
        )
        self._sync_header(force_render=False)
        logger.info("RichPromptToolkitUI started and listening")

    async def run(self) -> None:
        self._running = True
        self._renderer.render_banner()
        self._renderer.start_live_session()
        self._sync_header(force_render=True)

        try:
            while self._running:
                if self._current_state != "idle":
                    await asyncio.sleep(0.1)
                    continue

                await self._drain_tool_output_queue()

                if self._current_state != "idle":
                    continue

                prompt = self._get_prompt()
                try:
                    self._renderer.suspend_live_session()
                    try:
                        user_text = await self._input_handler.prompt(prompt)
                    finally:
                        self._renderer.resume_live_session()
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
        finally:
            self._renderer.stop_live_session()

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
        self._header.state = status
        self._header.state_message = message
        self._sync_header(force_render=False)

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
        self._renderer.clear_stream_visual_state()
        self._renderer.render_tool_confirmation(tool_name, parameters)
        self._renderer.suspend_live_session()
        try:
            result = await self._input_handler.confirm_tool_execution(
                tool_name=tool_name,
                parameters=parameters,
            )
        finally:
            self._renderer.resume_live_session()
            self._renderer.refresh_frame(force=True)

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
        success = bool(data.get("success", False))
        output = data.get("output")
        error = data.get("error")
        tool_name = str(data.get("tool_name", "") or "tool")
        output_text = "" if output is None else str(output)
        has_large_output = bool(output is not None and self._is_large_output(output_text))

        self._renderer.render_tool_output_preview(
            success=success,
            output=output,
            error=error,
            full_output_available=has_large_output,
        )

        if output is None:
            return
        if not has_large_output:
            return

        record = ToolOutputRecord(
            tool_name=tool_name,
            success=success,
            output_text=output_text,
            output_lines=len(output_text.splitlines()),
            output_chars=len(output_text),
        )
        self._pending_tool_outputs.append(record)
        while len(self._pending_tool_outputs) > self.TOOL_OUTPUT_QUEUE_MAX:
            self._pending_tool_outputs.popleft()
            self._renderer.render_warning(
                "Tool output viewer queue overflow. Oldest output discarded."
            )

    async def _handle_tool_progress(self, data: dict) -> None:
        tool_name = str(data.get("tool_name", "") or "tool")
        tool_call_id = str(data.get("tool_call_id", "") or tool_name)
        progress = data.get("progress")
        message = str(data.get("message", "") or "")
        signature = (progress, message)
        if self._tool_progress_seen.get(tool_call_id) == signature:
            return
        self._tool_progress_seen[tool_call_id] = signature
        self._renderer.render_tool_progress(
            tool_name=tool_name,
            progress=progress,
            message=message,
        )

    async def _handle_tool_complete(self, data: dict) -> None:
        tool_call_id = str(data.get("tool_call_id", "") or "")
        if tool_call_id:
            self._tool_progress_seen.pop(tool_call_id, None)
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
        self._apply_info_to_header(data)
        if not self._verbose_ui:
            return
        message = data.get("message", str(data))
        self._renderer.render_info(message)

    async def _handle_auto_confirm_changed(self, data: dict) -> None:
        self._auto_confirm = bool(data.get("auto_confirm", False))
        self._header.auto_confirm = self._auto_confirm
        self._sync_header(force_render=False)
        state = "enabled" if self._auto_confirm else "disabled"
        self._renderer.render_info(f"Auto-confirm {state}")

    async def _handle_model_switched(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        self._header.model = str(
            data.get("model")
            or data.get("active_model")
            or data.get("name")
            or self._header.model
        )
        self._sync_header(force_render=False)

    async def _handle_provider_switched(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        self._header.provider = str(
            data.get("provider")
            or data.get("llm_provider")
            or data.get("name")
            or self._header.provider
        )
        self._sync_header(force_render=False)

    async def _drain_tool_output_queue(self) -> None:
        while self._pending_tool_outputs and self._current_state == "idle":
            record = self._pending_tool_outputs.popleft()
            self._renderer.render_info(
                f"Large tool output available: {record.tool_name} ({record.output_chars} chars)"
            )
            self._renderer.suspend_live_session()
            try:
                show_full = await self._input_handler.confirm_yes_no(
                    f"Show full output for {record.tool_name}?",
                    default=False,
                )
            finally:
                self._renderer.resume_live_session()
                self._renderer.refresh_frame(force=True)
            if not show_full:
                continue
            shown, truncated, omitted = self._apply_output_cap(record.output_text)
            self._renderer.render_tool_output_full(
                tool_name=record.tool_name,
                output_text=shown,
                truncated=truncated,
                omitted_chars=omitted,
            )

    def _sync_header(self, *, force_render: bool) -> None:
        changed = self._renderer.update_header(**self._header.as_renderer_payload())
        if changed or force_render:
            self._renderer.refresh_frame(force=True)

    def _apply_info_to_header(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        message = str(data.get("message", "") or "")
        payload = data.get("data") if isinstance(data.get("data"), dict) else {}
        changed = False

        if message in {"Runtime configured", "Provider configured"}:
            provider = payload.get("provider")
            model = payload.get("active_model")
            if provider is not None and str(provider) != self._header.provider:
                self._header.provider = str(provider)
                changed = True
            if model is not None and str(model) != self._header.model:
                self._header.model = str(model)
                changed = True
        elif message == "Context updated":
            total_tokens = int(payload.get("total_tokens", self._header.total_tokens) or 0)
            message_count = int(payload.get("message_count", self._header.message_count) or 0)
            loaded_files = int(
                payload.get("loaded_files_count", self._header.loaded_files_count) or 0
            )
            context_limit = int(payload.get("context_limit", self._header.context_limit) or 0)
            if total_tokens != self._header.total_tokens:
                self._header.total_tokens = total_tokens
                changed = True
            if message_count != self._header.message_count:
                self._header.message_count = message_count
                changed = True
            if loaded_files != self._header.loaded_files_count:
                self._header.loaded_files_count = loaded_files
                changed = True
            if context_limit != self._header.context_limit:
                self._header.context_limit = context_limit
                changed = True

        if changed:
            self._sync_header(force_render=False)

    def _normalize_pass_id(self, pass_id: Any) -> str:
        text = str(pass_id).strip() if pass_id is not None else ""
        return text or self._default_pass_id

    @classmethod
    def _is_large_output(cls, output_text: str) -> bool:
        if len(output_text) > cls.LARGE_OUTPUT_CHAR_THRESHOLD:
            return True
        return len(output_text.splitlines()) > cls.LARGE_OUTPUT_LINE_THRESHOLD

    @classmethod
    def _apply_output_cap(cls, output_text: str) -> tuple[str, bool, int]:
        if len(output_text) <= cls.FULL_OUTPUT_SOFT_CAP:
            return output_text, False, 0
        shown = output_text[: cls.FULL_OUTPUT_SOFT_CAP]
        omitted = len(output_text) - cls.FULL_OUTPUT_SOFT_CAP
        return shown, True, omitted
