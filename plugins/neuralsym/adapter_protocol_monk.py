"""Protocol Monk adapter for NeuralSym."""

from __future__ import annotations

import time
import uuid
from typing import Any

from protocol_monk.agent.structs import AgentResponse, Message, ToolResult, ToolRequest, UserRequest

from .config import load_neuralsym_settings
from .models import (
    AssistantPassObservation,
    CorrelationRef,
    ExplicitUserPreferenceObservation,
    ToolResultObservation,
    UserInputObservation,
)
from .observer import sort_parameter_keys
from .runtime import NeuralSymRuntime


class ProtocolMonkNeuralSymAdapter:
    """Translate Protocol Monk runtime activity into NeuralSym observations."""

    def __init__(self, runtime: NeuralSymRuntime):
        self._runtime = runtime
        self._workspace_id = runtime.settings.workspace_id

    async def start(self) -> None:
        await self._runtime.start()

    async def stop(self) -> None:
        await self._runtime.stop()

    async def on_user_input(self, payload: UserRequest) -> None:
        observation = UserInputObservation(
            workspace_id=self._workspace_id,
            request_id=str(payload.request_id),
            source=str(payload.source),
            text_length=len(str(payload.text or "")),
            has_context=bool(payload.context),
            correlation=CorrelationRef(turn_id=str(payload.request_id)),
        )
        await self._runtime.observe(observation)

    async def on_assistant_pass(
        self,
        response: AgentResponse,
        *,
        turn_id: str,
        round_index: int,
        valid_tool_calls: list[ToolRequest],
    ) -> None:
        observation = AssistantPassObservation(
            workspace_id=self._workspace_id,
            response_pass_id=str(response.pass_id or ""),
            content_length=len(str(response.content or "")),
            thinking_length=len(str(response.thinking or "")),
            tool_call_count=len(valid_tool_calls),
            tool_call_names=[str(req.name) for req in valid_tool_calls],
            total_tokens=int(response.total_tokens or response.tokens or 0),
            correlation=CorrelationRef(
                turn_id=turn_id,
                pass_id=str(response.pass_id or ""),
                round_index=round_index,
            ),
        )
        await self._runtime.observe(observation)

    async def on_tool_result(
        self,
        result: ToolResult,
        *,
        turn_id: str,
        pass_id: str,
        round_index: int,
        tool_index: int,
    ) -> None:
        correlation = CorrelationRef(
            turn_id=turn_id,
            pass_id=pass_id,
            tool_call_id=str(result.call_id),
            round_index=round_index,
            tool_index=tool_index,
        )
        observation = ToolResultObservation(
            workspace_id=self._workspace_id,
            tool_name=str(result.tool_name),
            success=bool(result.success),
            duration_seconds=float(result.duration or 0.0),
            output_kind=result.output_kind,
            error_code=result.error_code,
            had_error=bool(result.error),
            request_parameter_keys=sort_parameter_keys(result.request_parameters),
            correlation=correlation,
        )
        await self._runtime.observe(observation)

        if result.error_code == "user_rejected":
            explicit_override = ExplicitUserPreferenceObservation(
                workspace_id=self._workspace_id,
                signal_kind="explicit_user_override",
                override_kind="avoid_tool",
                target_tool_name=str(result.tool_name),
                source_kind="tool_rejection",
                correlation=correlation,
            )
            await self._runtime.observe(explicit_override)

    async def build_system_message(
        self,
        *,
        turn_id: str | None = None,
        round_index: int | None = None,
    ) -> Message | None:
        content = await self._runtime.get_advice_message(
            turn_id=turn_id,
            round_index=round_index,
        )
        if not content:
            return None
        return Message(
            role="system",
            content=content,
            timestamp=time.time(),
            metadata={
                "id": str(uuid.uuid4()),
                "source": "neuralsym",
                "ephemeral": True,
                "turn_id": turn_id,
                "round_index": round_index,
            },
        )

    def runtime_state(self):
        return self._runtime.get_runtime_state()


async def build_protocol_monk_neuralsym_adapter(
    host_settings: Any,
) -> ProtocolMonkNeuralSymAdapter | None:
    """Build and start a NeuralSym adapter from host settings."""

    settings = load_neuralsym_settings(host_settings)
    if not settings.enabled:
        return None

    runtime = NeuralSymRuntime(settings)
    adapter = ProtocolMonkNeuralSymAdapter(runtime)
    await adapter.start()
    return adapter
