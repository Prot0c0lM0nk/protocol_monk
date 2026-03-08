import asyncio
import json
import logging
import time
import uuid
from typing import List, Optional, Any, Dict, Awaitable, Callable

from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.agent.structs import (
    AgentResponse,
    ToolRequest,
    ToolResult,
)
from protocol_monk.agent.usage_ledger import normalize_provider_usage
from protocol_monk.agent.core.execution import ToolExecutor
from protocol_monk.agent.core.state_machine import AgentState
from protocol_monk.tools.registry import ToolRegistry
from protocol_monk.config.settings import Settings

# Note: BaseProvider import assumed from providers.base (interface)
# from protocol_monk.providers.base import BaseProvider

logger = logging.getLogger("LogicLoops")


def _build_correlation(
    *,
    turn_id: str | None = None,
    pass_id: str | None = None,
    tool_call_id: str | None = None,
    round_index: int | None = None,
    tool_index: int | None = None,
    sequence: int | None = None,
) -> Dict[str, Any]:
    correlation: Dict[str, Any] = {}
    if turn_id:
        correlation["turn_id"] = turn_id
    if pass_id:
        correlation["pass_id"] = pass_id
    if tool_call_id:
        correlation["tool_call_id"] = tool_call_id
    if round_index is not None:
        correlation["round_index"] = round_index
    if tool_index is not None:
        correlation["tool_index"] = tool_index
    if sequence is not None:
        correlation["sequence"] = sequence
    return correlation

# --- THINKING LOOP ---


async def run_thinking_loop(
    context_history: List[Any],
    provider: Any,
    bus: EventBus,
    registry: ToolRegistry,
    settings: Settings,  # NEW: Add settings parameter
    turn_id: str,
    round_index: int = 0,
    preflight_metrics: Optional[Dict[str, Any]] = None,
) -> AgentResponse:
    """
    Consumes ProviderSignals and builds the response.
    """
    pass_id = str(uuid.uuid4())
    await bus.emit(
        EventTypes.THINKING_STARTED,
        _build_correlation(
            turn_id=turn_id,
            pass_id=pass_id,
            round_index=round_index,
        ),
    )
    full_text = ""
    full_thinking = ""
    tool_requests: List[ToolRequest] = []
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    provider_metrics: Dict[str, Any] = {}
    chunk_sequence = 0
    content_chunk_count = 0
    thinking_chunk_count = 0

    # Get tool definitions to send to provider
    tool_definitions = registry.get_openai_tools()

    # Use model name and parameters from settings
    model_name = settings.active_model_name
    context_limit = int(getattr(settings, "context_window_limit", 0) or 0)
    estimate = dict(preflight_metrics or {})
    estimated_context_tokens = int(
        estimate.get("estimated_next_request_tokens", 0) or 0
    )
    if estimated_context_tokens <= 0:
        estimated_context_tokens = sum(
            len(getattr(msg, "content", "") or "") // 4 for msg in context_history
        )
    await bus.emit(
        EventTypes.INFO,
        {
            "message": "Thinking loop context diagnostics",
            "data": {
                "estimated_tokens": estimated_context_tokens,
                "reserved_completion_tokens": int(
                    estimate.get("reserved_completion_tokens", 0) or 0
                ),
                "tool_count": len(tool_definitions),
                "context_limit": context_limit,
                "message_count": len(context_history),
                "model_name": model_name,
                "correlation": _build_correlation(
                    turn_id=turn_id,
                    pass_id=pass_id,
                    round_index=round_index,
                ),
            },
            **_build_correlation(
                turn_id=turn_id,
                pass_id=pass_id,
                round_index=round_index,
            ),
        },
    )
    if (
        context_limit > 0
        and estimated_context_tokens
        + int(estimate.get("reserved_completion_tokens", 0) or 0)
        >= context_limit
    ):
        await bus.emit(
            EventTypes.WARNING,
            {
                "message": "Context may overflow model window",
                "details": (
                    f"estimated_tokens={estimated_context_tokens} "
                    f"reserved_completion_tokens={int(estimate.get('reserved_completion_tokens', 0) or 0)} "
                    f"limit={context_limit} model={model_name}"
                ),
                **_build_correlation(
                    turn_id=turn_id,
                    pass_id=pass_id,
                    round_index=round_index,
                ),
            },
        )

    try:
        async for signal in provider.stream_chat(
            context_history,
            model_name,
            tool_definitions,
            options=settings.model_parameters,  # Pass model-specific params
        ):
            if signal.type == "content":
                full_text += signal.data
                content_chunk_count += 1
                chunk_sequence += 1
                await bus.emit(
                    EventTypes.STREAM_CHUNK,
                    {
                        "chunk": signal.data,
                        "channel": "content",
                        "turn_id": turn_id,
                        "pass_id": pass_id,
                        "round_index": round_index,
                        "sequence": chunk_sequence,
                    },
                )

            elif signal.type == "thinking":
                full_thinking += signal.data
                thinking_chunk_count += 1
                chunk_sequence += 1
                await bus.emit(
                    EventTypes.STREAM_CHUNK,
                    {
                        "chunk": signal.data,
                        "thinking": signal.data,
                        "channel": "thinking",
                        "turn_id": turn_id,
                        "pass_id": pass_id,
                        "round_index": round_index,
                        "sequence": chunk_sequence,
                    },
                )

            elif signal.type == "tool_call":
                req: ToolRequest = signal.data
                req.name = str(req.name or "").strip()
                if not req.name:
                    await bus.emit(
                        EventTypes.WARNING,
                        {
                            "message": "Provider emitted malformed tool call",
                            "details": "Tool call function name was empty.",
                            "data": {
                                "tool_call_id": req.call_id,
                                "parameters": req.parameters,
                                "metadata": req.metadata,
                            },
                            **_build_correlation(
                                turn_id=turn_id,
                                pass_id=pass_id,
                                tool_call_id=req.call_id,
                                round_index=round_index,
                            ),
                        },
                    )
                tool_requests.append(req)
                logger.debug(f"Received Tool Call: {req.name}")

            elif signal.type == "metrics":
                data = signal.data or {}
                provider_metrics = dict(data)
                normalized_usage = normalize_provider_usage(provider_metrics)
                prompt_tokens = normalized_usage.get("prompt_tokens")
                completion_tokens = normalized_usage.get("completion_tokens")
                total_tokens = normalized_usage.get("total_tokens")

                metrics_summary = {
                    "provider": data.get("provider"),
                    "request_model": data.get("request_model"),
                    "response_model": data.get("response_model") or data.get("model"),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "usage": data.get("usage"),
                    "finish_reasons": data.get("finish_reasons"),
                    "chunk_count": data.get("chunk_count"),
                    "correlation": _build_correlation(
                        turn_id=turn_id,
                        pass_id=pass_id,
                        round_index=round_index,
                    ),
                }
                await bus.emit(
                    EventTypes.INFO,
                    {
                        "message": "Provider metrics",
                        "data": metrics_summary,
                        **_build_correlation(
                            turn_id=turn_id,
                            pass_id=pass_id,
                            round_index=round_index,
                        ),
                    },
                )
                logger.debug("Provider metrics payload: %s", data)

            elif signal.type == "error":
                logger.error(f"Provider Error Signal: {signal.data}")
                await bus.emit(
                    EventTypes.ERROR,
                    {
                        "message": "Provider emitted an error signal",
                        "details": str(signal.data),
                        **_build_correlation(
                            turn_id=turn_id,
                            pass_id=pass_id,
                            round_index=round_index,
                        ),
                    },
                )

    except asyncio.CancelledError:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Thinking loop cancelled by caller.", exc_info=True)
        else:
            logger.info("Thinking loop cancelled by caller.")
        raise
    except Exception as e:
        logger.error(f"Loop Crash: {e}", exc_info=True)
        # Don't crash the agent, just return what we have

    await bus.emit(
        EventTypes.THINKING_STOPPED,
        _build_correlation(
            turn_id=turn_id,
            pass_id=pass_id,
            round_index=round_index,
        ),
    )

    response = AgentResponse(
        content=full_text,
        tool_calls=tool_requests,
        tokens=(
            int(total_tokens)
            if isinstance(total_tokens, int) and total_tokens >= 0
            else len(full_text) // 4
        ),
        thinking=full_thinking,
        pass_id=pass_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=(
            int(total_tokens)
            if isinstance(total_tokens, int) and total_tokens >= 0
            else len(full_text) // 4
        ),
        provider_metrics=provider_metrics,
    )

    await bus.emit(
        EventTypes.INFO,
        {
            "message": "Thinking loop summary",
            "data": {
                "pass_id": pass_id,
                "turn_id": turn_id,
                "round_index": round_index,
                "content_chunks": content_chunk_count,
                "thinking_chunks": thinking_chunk_count,
                "content_len": len(full_text),
                "thinking_len": len(full_thinking),
                "tool_calls": len(tool_requests),
            },
            **_build_correlation(
                turn_id=turn_id,
                pass_id=pass_id,
                round_index=round_index,
            ),
        },
    )

    if not full_text and not tool_requests:
        await bus.emit(
            EventTypes.WARNING,
            {
                "message": "Provider produced empty assistant content",
                "details": (
                    f"pass_id={pass_id} "
                    f"thinking_len={len(full_thinking)} "
                    f"tokens={response.tokens}"
                ),
                **_build_correlation(
                    turn_id=turn_id,
                    pass_id=pass_id,
                    round_index=round_index,
                ),
            },
        )

    await bus.emit(
        EventTypes.RESPONSE_COMPLETE,
        {
            "pass_id": response.pass_id,
            "turn_id": turn_id,
            "round_index": round_index,
            "content": response.content,
            "thinking": response.thinking,
            "tokens": response.tokens,
            "prompt_tokens": response.prompt_tokens,
            "completion_tokens": response.completion_tokens,
            "total_tokens": response.total_tokens,
            "tool_calls": response.tool_calls,
            # Keep compatibility for any existing consumers while transitioning.
            "has_tool_calls": bool(response.tool_calls),
        },
    )

    return response


def _parse_tool_json(data: Dict) -> Optional[ToolRequest]:
    """Helper to convert raw JSON to ToolRequest."""
    if "tool" in data and "parameters" in data:
        # Standardize standard format
        return ToolRequest(
            name=data["tool"],
            parameters=data["parameters"],
            call_id=str(time.time()),  # Gen ID if missing
            requires_confirmation=False,  # Will be checked against registry later
        )
    # Handle direct function call format (OpenAI style)
    if "name" in data and "arguments" in data:
        return ToolRequest(
            name=data["name"],
            parameters=(
                data["arguments"]
                if isinstance(data["arguments"], dict)
                else json.loads(data["arguments"])
            ),
            call_id=str(time.time()),
            requires_confirmation=False,
        )
    return None


# --- ACTION LOOP ---


async def run_action_loop(
    tool_req: ToolRequest,
    registry: ToolRegistry,
    bus: EventBus,
    executor: ToolExecutor,
    turn_id: str,
    pass_id: str,
    round_index: int,
    tool_index: int,
    confirmation_future: Optional[asyncio.Future] = None,
    auto_approve: bool = False,
    set_status: Optional[Callable[..., Awaitable[None]]] = None,
) -> ToolResult:
    """
    Manages tool execution including the Confirmation Barrier.
    """
    requested_tool_name = str(getattr(tool_req, "name", "") or "").strip()
    tool_req.name = requested_tool_name
    event_tool_name = requested_tool_name or "__missing_tool_name__"

    tool_call_id = str(getattr(tool_req, "call_id", "") or "").strip()
    if not tool_call_id:
        tool_call_id = f"call_missing_{round_index}_{tool_index}_{int(time.time() * 1000)}"
        tool_req.call_id = tool_call_id
        await bus.emit(
            EventTypes.WARNING,
            {
                "message": "Tool call missing id; generated fallback id",
                "details": tool_call_id,
                "turn_id": turn_id,
                "pass_id": pass_id,
                "round_index": round_index,
                "tool_index": tool_index,
            },
        )
    else:
        tool_req.call_id = tool_call_id

    async def _emit_terminal_tool_events(
        result: ToolResult, *, emit_start: bool
    ) -> ToolResult:
        final_tool_name = str(result.tool_name or "").strip() or event_tool_name
        result.tool_name = final_tool_name

        if emit_start:
            await bus.emit(
                EventTypes.TOOL_EXECUTION_START,
                {
                    "tool_name": final_tool_name,
                    "parameters": tool_req.parameters,
                    "tool_call_id": result.call_id,
                    "requires_confirmation": bool(tool_req.requires_confirmation),
                    "turn_id": turn_id,
                    "pass_id": pass_id,
                    "round_index": round_index,
                    "tool_index": tool_index,
                },
            )

        await bus.emit(
            EventTypes.TOOL_RESULT,
            {
                "tool_name": final_tool_name,
                "tool_call_id": result.call_id,
                "output": result.output,
                "success": result.success,
                "error": result.error,
                "error_code": result.error_code,
                "output_kind": result.output_kind,
                "error_details": result.error_details,
                "turn_id": turn_id,
                "pass_id": pass_id,
                "round_index": round_index,
                "tool_index": tool_index,
            },
        )

        await bus.emit(
            EventTypes.TOOL_EXECUTION_COMPLETE,
            {
                "tool_name": final_tool_name,
                "tool_call_id": result.call_id,
                "success": result.success,
                "duration": result.duration,
                "turn_id": turn_id,
                "pass_id": pass_id,
                "round_index": round_index,
                "tool_index": tool_index,
            },
        )
        return result

    # 1. Lookup Tool Definition to check confirmation policy
    tool_def = registry.get_tool(tool_req.name)
    if not tool_def:
        return await _emit_terminal_tool_events(
            ToolResult(
                tool_name=event_tool_name,
                call_id=tool_req.call_id,
                success=False,
                output=None,
                duration=0,
                error=f"Tool {requested_tool_name or '<missing tool name>'} not registered.",
                error_code="tool_not_registered",
                output_kind="none",
                error_details={
                    "requested_tool_name": requested_tool_name or None,
                    "registered_tools": registry.list_tool_names(),
                },
                request_parameters=tool_req.parameters,
            ),
            emit_start=True,
        )

    # Update request with actual confirmation policy
    tool_req.requires_confirmation = tool_def.requires_confirmation

    await bus.emit(
        EventTypes.TOOL_EXECUTION_START,
        {
            "tool_name": event_tool_name,
            "parameters": tool_req.parameters,
            "tool_call_id": tool_req.call_id,
            "requires_confirmation": tool_req.requires_confirmation,
            "turn_id": turn_id,
            "pass_id": pass_id,
            "round_index": round_index,
            "tool_index": tool_index,
        },
    )

    # 2. Confirmation Barrier
    if tool_req.requires_confirmation:
        if auto_approve:
            await bus.emit(
                EventTypes.INFO,
                {
                    "message": f"Auto-approved tool execution: {tool_req.name}",
                    "tool_call_id": tool_req.call_id,
                    "turn_id": turn_id,
                    "pass_id": pass_id,
                    "round_index": round_index,
                    "tool_index": tool_index,
                },
            )
        else:
            if not confirmation_future:
                # Should not happen if Service wired correctly
                return await _emit_terminal_tool_events(
                    ToolResult(
                        event_tool_name,
                        tool_req.call_id,
                        False,
                        None,
                        0,
                        "Internal Error: Missing confirmation future",
                        error_code="missing_confirmation_future",
                        output_kind="none",
                        request_parameters=tool_req.parameters,
                    ),
                    emit_start=False,
                )

            await bus.emit(
                EventTypes.TOOL_CONFIRMATION_REQUESTED,
                {
                    "tool_name": tool_req.name,
                    "parameters": tool_req.parameters,
                    "tool_call_id": tool_req.call_id,
                    "reason": "Sensitive Operation",
                    "turn_id": turn_id,
                    "pass_id": pass_id,
                    "round_index": round_index,
                    "tool_index": tool_index,
                },
            )

            if set_status is not None:
                await set_status(
                    AgentState.PAUSED,
                    "Waiting for approval...",
                    turn_id=turn_id,
                    pass_id=pass_id,
                    round_index=round_index,
                    tool_call_id=tool_req.call_id,
                    tool_index=tool_index,
                )
            else:
                await bus.emit(
                    EventTypes.STATUS_CHANGED,
                    {
                        "status": AgentState.PAUSED,
                        "message": "Waiting for approval...",
                        "turn_id": turn_id,
                        "pass_id": pass_id,
                        "round_index": round_index,
                        "tool_call_id": tool_req.call_id,
                        "tool_index": tool_index,
                    },
                )

            # WAIT HERE
            try:
                decision_payload = (
                    await confirmation_future
                )  # Waiting for user decision indefinitely is ok.
            except asyncio.CancelledError:
                return await _emit_terminal_tool_events(
                    ToolResult(
                        event_tool_name,
                        tool_req.call_id,
                        False,
                        None,
                        0,
                        "Cancelled",
                        error_code="confirmation_cancelled",
                        output_kind="none",
                        request_parameters=tool_req.parameters,
                    ),
                    emit_start=False,
                )

            # Resume
            if set_status is not None:
                await set_status(
                    AgentState.EXECUTING,
                    "Resuming...",
                    turn_id=turn_id,
                    pass_id=pass_id,
                    round_index=round_index,
                    tool_call_id=tool_req.call_id,
                    tool_index=tool_index,
                )
            else:
                await bus.emit(
                    EventTypes.STATUS_CHANGED,
                    {
                        "status": AgentState.EXECUTING,
                        "message": "Resuming...",
                        "turn_id": turn_id,
                        "pass_id": pass_id,
                        "round_index": round_index,
                        "tool_call_id": tool_req.call_id,
                        "tool_index": tool_index,
                    },
                )

            if decision_payload.decision == "rejected":
                return await _emit_terminal_tool_events(
                    ToolResult(
                        event_tool_name,
                        tool_req.call_id,
                        False,
                        None,
                        0,
                        "User rejected execution",
                        error_code="user_rejected",
                        output_kind="none",
                        request_parameters=tool_req.parameters,
                    ),
                    emit_start=False,
                )

    # 3. Execution
    await bus.emit(
        EventTypes.TOOL_EXECUTION_PROGRESS,
        {
            "tool_name": event_tool_name,
            "tool_call_id": tool_req.call_id,
            "progress": 0,
            "message": "Starting...",
            "turn_id": turn_id,
            "pass_id": pass_id,
            "round_index": round_index,
            "tool_index": tool_index,
        },
    )

    result = await executor.execute(tool_req, registry)
    return await _emit_terminal_tool_events(result, emit_start=False)
