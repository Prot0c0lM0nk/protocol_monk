"""Mock agent service for Textual UI development and tests."""

from __future__ import annotations

import time
import uuid
from typing import Any

from protocol_monk.agent.structs import AgentStatus, ConfirmationResponse, UserRequest
from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes


class MockAgentService:
    """A deterministic event-driven mock that follows the current bus contract."""

    def __init__(self, bus: EventBus):
        self._bus = bus
        self._started = False
        self._pending_tools: dict[str, str] = {}

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        await self._bus.subscribe(EventTypes.USER_INPUT_SUBMITTED, self._on_user_input)
        await self._bus.subscribe(
            EventTypes.TOOL_CONFIRMATION_SUBMITTED,
            self._on_tool_confirmation,
        )

    async def _on_user_input(self, payload: UserRequest | dict[str, Any]) -> None:
        text = payload.text if hasattr(payload, "text") else str(payload.get("text", ""))
        text = (text or "").strip()
        if not text:
            return

        await self._bus.emit(
            EventTypes.STATUS_CHANGED,
            AgentStatus(status="thinking", message="Mock agent reasoning"),
        )
        await self._bus.emit(
            EventTypes.THINKING_STARTED,
            {"message": "Mock agent reasoning"},
        )
        await self._bus.emit(
            EventTypes.STREAM_CHUNK,
            {"chunk": "Mock reasoning in progress...", "channel": "thinking"},
        )

        if "tool" in text.lower():
            tool_call_id = str(uuid.uuid4())
            self._pending_tools[tool_call_id] = text
            await self._bus.emit(
                EventTypes.STATUS_CHANGED,
                AgentStatus(status="paused", message="Waiting for approval"),
            )
            await self._bus.emit(
                EventTypes.TOOL_CONFIRMATION_REQUESTED,
                {
                    "tool_name": "execute_command",
                    "parameters": {"command": "pwd"},
                    "tool_call_id": tool_call_id,
                    "reason": "Mock sensitive operation",
                },
            )
            return

        await self._stream_content(["Mock response: ", text])
        await self._bus.emit(
            EventTypes.RESPONSE_COMPLETE,
            {
                "content": f"Mock response: {text}",
                "thinking": "Mock reasoning in progress...",
                "tool_calls": [],
                "has_tool_calls": False,
            },
        )
        await self._bus.emit(EventTypes.THINKING_STOPPED, {"message": "Done"})
        await self._bus.emit(
            EventTypes.STATUS_CHANGED,
            AgentStatus(status="idle", message="Ready"),
        )

    async def _on_tool_confirmation(
        self,
        payload: ConfirmationResponse | dict[str, Any],
    ) -> None:
        tool_call_id = (
            payload.tool_call_id if hasattr(payload, "tool_call_id") else payload.get("tool_call_id", "")
        )
        decision = payload.decision if hasattr(payload, "decision") else payload.get("decision", "rejected")

        if not tool_call_id or tool_call_id not in self._pending_tools:
            return

        text = self._pending_tools.pop(tool_call_id)

        await self._bus.emit(
            EventTypes.STATUS_CHANGED,
            AgentStatus(status="executing", message="Applying tool decision"),
        )

        if decision == "approved":
            await self._bus.emit(
                EventTypes.TOOL_EXECUTION_START,
                {
                    "tool_name": "execute_command",
                    "parameters": {"command": "pwd"},
                    "tool_call_id": tool_call_id,
                    "requires_confirmation": True,
                },
            )
            await self._bus.emit(
                EventTypes.TOOL_EXECUTION_PROGRESS,
                {
                    "tool_name": "execute_command",
                    "tool_call_id": tool_call_id,
                    "progress": 100,
                    "message": "Mock command complete",
                },
            )
            await self._bus.emit(
                EventTypes.TOOL_RESULT,
                {
                    "tool_name": "execute_command",
                    "tool_call_id": tool_call_id,
                    "output": "mock:/workspace",
                    "success": True,
                    "error": None,
                    "error_code": None,
                    "output_kind": "str",
                    "error_details": None,
                },
            )
            await self._bus.emit(
                EventTypes.TOOL_EXECUTION_COMPLETE,
                {
                    "tool_name": "execute_command",
                    "tool_call_id": tool_call_id,
                    "success": True,
                    "duration": 0.01,
                },
            )
            await self._stream_content(["Tool approved for: ", text])
        else:
            await self._bus.emit(
                EventTypes.TOOL_RESULT,
                {
                    "tool_name": "execute_command",
                    "tool_call_id": tool_call_id,
                    "output": None,
                    "success": False,
                    "error": "User rejected execution",
                    "error_code": "user_rejected",
                    "output_kind": "none",
                    "error_details": None,
                },
            )
            await self._stream_content(["Tool rejected for: ", text])

        await self._bus.emit(
            EventTypes.RESPONSE_COMPLETE,
            {
                "content": "mock tool flow complete",
                "thinking": "",
                "tool_calls": [],
                "has_tool_calls": False,
            },
        )
        await self._bus.emit(EventTypes.THINKING_STOPPED, {"message": "Done"})
        await self._bus.emit(
            EventTypes.STATUS_CHANGED,
            AgentStatus(status="idle", message="Ready"),
        )

    async def _stream_content(self, chunks: list[str]) -> None:
        for chunk in chunks:
            await self._bus.emit(
                EventTypes.STREAM_CHUNK,
                {"chunk": chunk, "channel": "content", "sequence": int(time.time() * 1000)},
            )
