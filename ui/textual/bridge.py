"""Bridge protocol events into Textual messages and modal interactions."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from protocol_monk.agent.structs import ConfirmationResponse
from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.ui.textual.messages import (
    AgentStatusUpdate,
    AgentStreamChunk,
    AgentSystemMessage,
    AgentToolResult,
)
from protocol_monk.ui.textual.models.phase_state import normalize_phase


class TextualEventBridge:
    def __init__(self, app: Any, bus: EventBus):
        self._app = app
        self._bus = bus
        self._started = False
        self._status = "idle"
        self._detail = "Ready"
        self._provider: str | None = None
        self._model: str | None = None
        self._auto_confirm: bool | None = None
        self._working_dir: str | None = None
        self._confirmation_lock = asyncio.Lock()
        self._confirmation_tasks: set[asyncio.Task] = set()

    async def start(self) -> None:
        if self._started:
            return
        self._started = True

        await self._bus.subscribe(EventTypes.STATUS_CHANGED, self._on_status_changed)
        await self._bus.subscribe(EventTypes.STREAM_CHUNK, self._on_stream_chunk)
        await self._bus.subscribe(EventTypes.THINKING_STARTED, self._on_thinking_started)
        await self._bus.subscribe(EventTypes.THINKING_STOPPED, self._on_thinking_stopped)
        await self._bus.subscribe(EventTypes.RESPONSE_COMPLETE, self._on_response_complete)
        await self._bus.subscribe(EventTypes.TOOL_RESULT, self._on_tool_result)
        await self._bus.subscribe(
            EventTypes.TOOL_CONFIRMATION_REQUESTED,
            self._on_tool_confirmation_requested,
        )
        await self._bus.subscribe(EventTypes.INFO, self._on_info)
        await self._bus.subscribe(EventTypes.WARNING, self._on_warning)
        await self._bus.subscribe(EventTypes.ERROR, self._on_error)
        await self._bus.subscribe(
            EventTypes.AUTO_CONFIRM_CHANGED, self._on_auto_confirm_changed
        )

        settings = getattr(self._app, "settings", None)
        if settings is not None:
            provider = getattr(settings, "llm_provider", None)
            model = getattr(settings, "active_model_name", None)
            auto_confirm = getattr(settings, "auto_confirm", None)
            working_dir = getattr(settings, "workspace_root", None)
            self._provider = str(provider) if provider else self._provider
            self._model = str(model) if model else self._model
            if auto_confirm is not None:
                self._auto_confirm = bool(auto_confirm)
            if working_dir is not None:
                self._working_dir = str(working_dir)
            self._post_status_update()

    async def _on_status_changed(self, payload: Any) -> None:
        status = getattr(payload, "status", None)
        detail = getattr(payload, "message", "")

        if isinstance(payload, dict):
            status = payload.get("status", status)
            detail = payload.get("message", detail)

        self._status = normalize_phase(getattr(status, "value", status))
        self._detail = str(detail or "")
        self._post_status_update()

    async def _on_stream_chunk(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        chunk = payload.get("chunk")
        if not chunk:
            return
        channel = str(payload.get("channel") or "content")
        self._app.post_message(AgentStreamChunk(str(chunk), channel=channel))

    async def _on_thinking_started(self, payload: Any) -> None:
        detail = ""
        if isinstance(payload, dict):
            detail = str(payload.get("message") or "")
        self._status = "thinking"
        self._detail = detail or "thinking"
        self._post_status_update()

    async def _on_thinking_stopped(self, _payload: Any) -> None:
        self._status = "executing"
        self._detail = "processing"
        self._post_status_update()

    async def _on_response_complete(self, _payload: dict) -> None:
        self._app.post_message(AgentSystemMessage("", level="response_complete"))

    async def _on_tool_result(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        self._app.post_message(AgentToolResult(payload=payload))

    async def _on_tool_confirmation_requested(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return

        tool_name = str(payload.get("tool_name") or "tool")
        parameters = payload.get("parameters") or {}
        tool_call_id = str(payload.get("tool_call_id") or "")
        if not tool_call_id:
            return

        # Never block the event-bus emit path on modal interaction.
        task = asyncio.create_task(
            self._resolve_tool_confirmation(tool_name, parameters, tool_call_id)
        )
        self._confirmation_tasks.add(task)
        task.add_done_callback(self._confirmation_tasks.discard)

    async def _resolve_tool_confirmation(
        self,
        tool_name: str,
        parameters: dict,
        tool_call_id: str,
    ) -> None:
        async with self._confirmation_lock:
            decision = "rejected"
            try:
                decision = await asyncio.wait_for(
                    self._app.request_tool_confirmation(tool_name, parameters),
                    timeout=130.0,
                )
            except asyncio.TimeoutError:
                decision = "rejected"

            if decision == "approved_auto":
                await self._bus.emit(
                    EventTypes.SYSTEM_COMMAND_ISSUED,
                    {"command": "toggle_auto_confirm", "auto_confirm": True},
                )
                decision = "approved"
            elif decision != "approved":
                decision = "rejected"

            response = ConfirmationResponse(
                tool_call_id=tool_call_id,
                decision=decision,
                timestamp=time.time(),
            )
            await self._bus.emit(EventTypes.TOOL_CONFIRMATION_SUBMITTED, response)

    async def _on_info(self, payload: Any) -> None:
        message = payload.get("message", "") if isinstance(payload, dict) else str(payload)
        if isinstance(payload, dict) and message == "Provider configured":
            data = payload.get("data", {}) or {}
            provider = data.get("provider")
            model = data.get("active_model")
            if provider is not None:
                self._provider = str(provider)
            if model is not None:
                self._model = str(model)
            self._post_status_update()
        if message:
            self._app.post_message(AgentSystemMessage(message, level="info"))

    async def _on_warning(self, payload: Any) -> None:
        message = payload.get("message", "") if isinstance(payload, dict) else str(payload)
        if message:
            self._app.post_message(AgentSystemMessage(message, level="warning"))

    async def _on_error(self, payload: Any) -> None:
        message = payload.get("message", "") if isinstance(payload, dict) else str(payload)
        if message:
            self._app.post_message(AgentSystemMessage(message, level="error"))

    async def _on_auto_confirm_changed(self, payload: Any) -> None:
        if isinstance(payload, dict) and "auto_confirm" in payload:
            self._auto_confirm = bool(payload.get("auto_confirm"))
            self._post_status_update()

    def _post_status_update(self) -> None:
        self._app.post_message(
            AgentStatusUpdate(
                status=self._status,
                detail=self._detail,
                provider=self._provider,
                model=self._model,
                auto_confirm=self._auto_confirm,
                working_dir=self._working_dir,
            )
        )
