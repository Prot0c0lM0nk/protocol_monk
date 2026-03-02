"""Primary Rich runtime UI for Protocol Monk."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Any

from protocol_monk.agent.structs import ConfirmationResponse, UserRequest
from protocol_monk.config.settings import Settings
from protocol_monk.protocol.command_dispatcher import (
    build_signoff_prompt,
    is_signoff_input,
)
from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.ui.rich.input_handler import RichInputHandler
from protocol_monk.ui.rich.renderer import RichRenderer
from protocol_monk.ui.rich.typewriter import TYPEWRITER_PRESETS, typewriter_print

logger = logging.getLogger("RichPromptToolkitUI")


@dataclass
class ToolOutputRecord:
    tool_name: str
    success: bool
    output_text: str
    output_lines: int
    output_chars: int
    duration: float = 0.0
    timestamp: float = 0.0


class RichPromptToolkitUI:
    """
    Rich runtime UI backed by prompt-toolkit input.

    Behavior intentionally mirrors the CLI fallback for command and approval semantics.
    Uses scrollback-native approach - content prints directly to terminal for natural
    scrollback, with transient streaming panel during AI responses.
    """

    LARGE_OUTPUT_CHAR_THRESHOLD = 160
    LARGE_OUTPUT_LINE_THRESHOLD = 6
    FULL_OUTPUT_SOFT_CAP = 20_000
    TOOL_OUTPUT_QUEUE_MAX = 10
    TOOL_RESULT_QUEUE_MAX = 20

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

        self._running = False
        self._current_state = "idle"
        self._pass_buffers: dict[str, dict[str, str]] = {}
        self._default_pass_id = "__legacy__"
        self._auto_confirm = bool(getattr(settings, "auto_confirm", False))
        self._verbose_ui = str(getattr(settings, "log_level", "INFO")).upper() == "DEBUG"
        self._confirmation_tasks: dict[str, asyncio.Task] = {}
        self._pending_tool_outputs: deque[ToolOutputRecord] = deque()
        self._tool_results: deque[ToolOutputRecord] = deque(maxlen=self.TOOL_RESULT_QUEUE_MAX)
        self._tool_progress_seen: dict[str, tuple[Any, str]] = {}
        self._tool_viewer_task: asyncio.Task | None = None

        self._status_symbols = {
            "idle": "idle",
            "thinking": "thinking...",
            "executing": "executing",
            "paused": "paused",
            "error": "error",
        }

        # Create input handler with Ctrl+O callback (after self._handle_ctrl_o is available)
        if input_handler is not None:
            self._input_handler = input_handler
        else:
            self._input_handler = RichInputHandler(on_ctrl_o=self._handle_ctrl_o)

    async def start(self) -> None:
        await self._bus.subscribe(EventTypes.STATUS_CHANGED, self._handle_status_changed)
        await self._bus.subscribe(EventTypes.THINKING_STARTED, self._handle_thinking_started)
        await self._bus.subscribe(EventTypes.THINKING_STOPPED, self._handle_thinking_stopped)
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
        await self._bus.subscribe(EventTypes.COMMAND_RESULT, self._handle_command_result)
        logger.info("RichPromptToolkitUI started and listening")

    async def run(self) -> None:
        self._running = True
        self._renderer.render_banner()

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
                    self._renderer.lock_for_input()
                    user_text = await self._input_handler.prompt(prompt)
                except (EOFError, KeyboardInterrupt):
                    self._renderer.render_info("Goodbye!")
                    self._running = False
                    break
                finally:
                    self._renderer.unlock_for_input()

                normalized = user_text.strip()
                if not normalized:
                    continue

                if self._is_signoff_command(normalized):
                    await self._run_signoff_and_shutdown(normalized)
                    break

                handled = await self._process_local_command(normalized)
                if handled:
                    continue

                await self._emit_user_input(normalized)
        finally:
            self._renderer.shutdown()

    async def stop(self) -> None:
        self._running = False
        for task in list(self._confirmation_tasks.values()):
            task.cancel()
        self._confirmation_tasks.clear()
        if self._tool_viewer_task is not None:
            self._tool_viewer_task.cancel()
            self._tool_viewer_task = None
        self._renderer.shutdown()
        logger.info("RichPromptToolkitUI stopped")

    async def _process_local_command(self, text: str) -> bool:
        cmd = text.strip()
        if not cmd.startswith("/"):
            return False
        await self._dispatch_slash_command(cmd)
        return True

    @staticmethod
    def _is_signoff_command(text: str) -> bool:
        return is_signoff_input(text)

    async def _dispatch_slash_command(self, text: str) -> None:
        await self._bus.emit(
            EventTypes.SYSTEM_COMMAND_ISSUED,
            {"command": "dispatch_slash", "text": text},
        )

    async def _run_signoff_and_shutdown(self, trigger: str) -> None:
        signoff_prompt = build_signoff_prompt(trigger)
        await self._emit_user_input(signoff_prompt)
        await self._render_shutdown_sequence()
        self._running = False

    async def _render_shutdown_sequence(self) -> None:
        await typewriter_print(
            "✠ The session is sealed.\n",
            config=TYPEWRITER_PRESETS["fast"],
            style="monk.text",
        )
        await typewriter_print(
            "✠ I now extinguish the console lamps and close this cell.\n",
            config=TYPEWRITER_PRESETS["fast"],
            style="muted",
        )

    def _get_prompt(self) -> str:
        return "✠☦✠> "

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

    async def _handle_thinking_started(self, data: Any) -> None:
        if isinstance(data, dict):
            message = str(data.get("message", "") or "")
        else:
            message = str(getattr(data, "message", "") or "")
        self._renderer.start_thinking(message or "Contemplating...")

    async def _handle_thinking_stopped(self, data: Any) -> None:
        _ = data
        self._renderer.stop_thinking()

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

        # Store ALL results for Ctrl+O viewer
        if output is not None:
            record = ToolOutputRecord(
                tool_name=tool_name,
                success=success,
                output_text=output_text,
                output_lines=len(output_text.splitlines()),
                output_chars=len(output_text),
                duration=0.0,  # Updated in _handle_tool_complete
                timestamp=time.time(),
            )
            self._tool_results.append(record)

        # Keep legacy large output handling for deferred viewing
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

        tool_name = str(data.get("tool_name", "") or "")
        duration = float(data.get("duration", 0.0))
        success = bool(data.get("success", False))

        # Update duration in most recent matching record
        for record in reversed(list(self._tool_results)):
            if record.tool_name == tool_name and record.duration == 0.0:
                record.duration = duration
                break

        self._renderer.render_tool_complete(
            tool_name=tool_name,
            success=success,
            duration=duration,
        )

    async def _handle_error(self, data: dict) -> None:
        message = data.get("message", str(data))
        self._renderer.render_error(message, recovered=bool(data.get("recovered", False)))

    async def _handle_warning(self, data: dict) -> None:
        message = data.get("message", str(data))
        self._renderer.render_warning(message)

    async def _handle_info(self, data: dict) -> None:
        if self._verbose_ui:
            message = data.get("message", str(data))
            self._renderer.render_info(message)

    async def _handle_auto_confirm_changed(self, data: dict) -> None:
        self._auto_confirm = bool(data.get("auto_confirm", False))
        state = "enabled" if self._auto_confirm else "disabled"
        self._renderer.render_info(f"Auto-confirm {state}")

    async def _handle_model_switched(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        model = str(
            data.get("model")
            or data.get("active_model")
            or data.get("name")
            or ""
        )
        if model:
            self._renderer.render_info(f"Model switched to: {model}")

    async def _handle_provider_switched(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        provider = str(
            data.get("provider")
            or data.get("llm_provider")
            or data.get("name")
            or ""
        )
        if provider:
            self._renderer.render_info(f"Provider switched to: {provider}")

    async def _handle_command_result(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        command = str(data.get("command", "") or "").strip().lower()
        ok = bool(data.get("ok", False))
        message = str(data.get("message", "") or "").strip()
        payload = data.get("data") if isinstance(data.get("data"), dict) else {}

        if command == "status" and ok:
            self._renderer.render_status_snapshot(payload)
            return
        if not message:
            return
        if ok:
            self._renderer.render_info(message)
        else:
            self._renderer.render_warning(message)

    async def _drain_tool_output_queue(self) -> None:
        while self._pending_tool_outputs and self._current_state == "idle":
            record = self._pending_tool_outputs.popleft()
            self._renderer.render_info(
                f"Large tool output available: {record.tool_name} ({record.output_chars} chars)"
            )
            self._renderer.lock_for_input()
            try:
                show_full = await self._input_handler.confirm_yes_no(
                    f"Show full output for {record.tool_name}?",
                    default=False,
                )
            finally:
                self._renderer.unlock_for_input()
            if not show_full:
                continue
            shown, truncated, omitted = self._apply_output_cap(record.output_text)
            self._renderer.render_tool_output_full(
                tool_name=record.tool_name,
                output_text=shown,
                truncated=truncated,
                omitted_chars=omitted,
            )

    def _handle_ctrl_o(self) -> None:
        """Handle Ctrl+O keypress - schedule viewer on main loop."""
        if self._tool_viewer_task is not None and not self._tool_viewer_task.done():
            return

        task = asyncio.create_task(self._show_tool_output_viewer())
        self._tool_viewer_task = task

        def _clear_task(_: asyncio.Task) -> None:
            if self._tool_viewer_task is task:
                self._tool_viewer_task = None

        task.add_done_callback(_clear_task)

    async def _show_tool_output_viewer(self) -> None:
        """Show panel with recent tool results, allow viewing full output.

        Uses a scrollback-native panel-based selection (no modal dialogs).
        """
        if not self._tool_results:
            self._renderer.render_info("No tool results available")
            return

        # Build options list (most recent first)
        options = []
        for record in reversed(list(self._tool_results)):
            status = "✓" if record.success else "✗"
            duration = f"{record.duration:.2f}s" if record.duration > 0 else "..."
            label = f"{status} {record.tool_name} [{duration}] ({record.output_chars} chars)"
            options.append(label)

        # Show panel and get selection
        self._renderer.lock_for_input()
        try:
            selected_index = await self._input_handler.select_from_list(
                title="Tool Results (Ctrl+O)",
                options=options,
                default_index=0,
            )
        finally:
            self._renderer.unlock_for_input()

        # Show full output for selection
        record = list(self._tool_results)[-(selected_index + 1)]
        shown, truncated, omitted = self._apply_output_cap(record.output_text)
        self._renderer.render_tool_output_full(
            tool_name=record.tool_name,
            output_text=shown,
            truncated=truncated,
            omitted_chars=omitted,
        )

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
