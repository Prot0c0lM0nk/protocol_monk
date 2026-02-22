import asyncio
import json
import logging
import time
import uuid
from typing import List, Optional, Any, Dict

from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.agent.structs import (
    AgentResponse,
    ToolRequest,
    ToolResult,
)
from protocol_monk.agent.core.execution import ToolExecutor
from protocol_monk.agent.core.state_machine import AgentState
from protocol_monk.tools.registry import ToolRegistry
from protocol_monk.config.settings import Settings

# Note: BaseProvider import assumed from providers.base (interface)
# from protocol_monk.providers.base import BaseProvider

logger = logging.getLogger("LogicLoops")

# --- THINKING LOOP ---


async def run_thinking_loop(
    context_history: List[Any],
    provider: Any,
    bus: EventBus,
    registry: ToolRegistry,
    settings: Settings,  # NEW: Add settings parameter
) -> AgentResponse:
    """
    Consumes ProviderSignals and builds the response.
    """
    await bus.emit(EventTypes.THINKING_STARTED)

    pass_id = str(uuid.uuid4())
    full_text = ""
    full_thinking = ""
    tool_requests: List[ToolRequest] = []
    token_usage = 0
    chunk_sequence = 0

    # Get tool definitions to send to provider
    tool_definitions = registry.get_openai_tools()

    # Use model name and parameters from settings
    model_name = settings.active_model_name
    context_limit = int(getattr(settings, "context_window_limit", 0) or 0)

    estimated_context_tokens = sum(
        len(getattr(msg, "content", "") or "") // 4 for msg in context_history
    )
    await bus.emit(
        EventTypes.INFO,
        {
            "message": "Thinking loop context diagnostics",
            "data": {
                "estimated_tokens": estimated_context_tokens,
                "context_limit": context_limit,
                "message_count": len(context_history),
                "model_name": model_name,
            },
        },
    )
    if context_limit > 0 and estimated_context_tokens >= context_limit:
        await bus.emit(
            EventTypes.WARNING,
            {
                "message": "Context may overflow model window",
                "details": (
                    f"estimated_tokens={estimated_context_tokens} "
                    f"limit={context_limit} model={model_name}"
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
                chunk_sequence += 1
                await bus.emit(
                    EventTypes.STREAM_CHUNK,
                    {
                        "chunk": signal.data,
                        "channel": "content",
                        "pass_id": pass_id,
                        "sequence": chunk_sequence,
                    },
                )

            elif signal.type == "thinking":
                full_thinking += signal.data
                chunk_sequence += 1
                await bus.emit(
                    EventTypes.STREAM_CHUNK,
                    {
                        "chunk": signal.data,
                        "thinking": signal.data,
                        "channel": "thinking",
                        "pass_id": pass_id,
                        "sequence": chunk_sequence,
                    },
                )

            elif signal.type == "tool_call":
                req: ToolRequest = signal.data
                tool_requests.append(req)
                logger.info(f"Received Tool Call: {req.name}")

            elif signal.type == "metrics":
                # Capture token counts
                data = signal.data or {}
                if "eval_count" in data:
                    token_usage = data["eval_count"]
                else:
                    usage = data.get("usage")
                    if isinstance(usage, dict):
                        total_tokens = usage.get("total_tokens")
                        if isinstance(total_tokens, int) and total_tokens > 0:
                            token_usage = total_tokens

                metrics_summary = {
                    "provider": data.get("provider"),
                    "request_model": data.get("request_model"),
                    "response_model": data.get("model"),
                    "usage": data.get("usage"),
                    "finish_reasons": data.get("finish_reasons"),
                    "chunk_count": data.get("chunk_count"),
                }
                await bus.emit(
                    EventTypes.INFO,
                    {
                        "message": "Provider metrics",
                        "data": metrics_summary,
                    },
                )
                logger.debug("Provider metrics payload: %s", data)

            elif signal.type == "error":
                logger.error(f"Provider Error Signal: {signal.data}")

    except asyncio.CancelledError:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Thinking loop cancelled by caller.", exc_info=True)
        else:
            logger.info("Thinking loop cancelled by caller.")
        raise
    except Exception as e:
        logger.error(f"Loop Crash: {e}", exc_info=True)
        # Don't crash the agent, just return what we have

    await bus.emit(EventTypes.THINKING_STOPPED)

    response = AgentResponse(
        content=full_text,
        tool_calls=tool_requests,
        tokens=token_usage if token_usage > 0 else len(full_text) // 4,
        thinking=full_thinking,
        pass_id=pass_id,
    )

    await bus.emit(
        EventTypes.RESPONSE_COMPLETE,
        {
            "pass_id": response.pass_id,
            "content": response.content,
            "thinking": response.thinking,
            "tokens": response.tokens,
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
    confirmation_future: Optional[asyncio.Future] = None,
    auto_approve: bool = False,
) -> ToolResult:
    """
    Manages tool execution including the Confirmation Barrier.
    """
    # 1. Lookup Tool Definition to check confirmation policy
    tool_def = registry.get_tool(tool_req.name)
    if not tool_def:
        return ToolResult(
            tool_name=tool_req.name,
            call_id=tool_req.call_id,
            success=False,
            output=None,
            duration=0,
            error=f"Tool {tool_req.name} not registered.",
            error_code="tool_not_registered",
            output_kind="none",
        )

    # Update request with actual confirmation policy
    tool_req.requires_confirmation = tool_def.requires_confirmation

    await bus.emit(
        EventTypes.TOOL_EXECUTION_START,
        {
            "tool_name": tool_req.name,
            "parameters": tool_req.parameters,
            "tool_call_id": tool_req.call_id,
            "requires_confirmation": tool_req.requires_confirmation,
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
                },
            )
        else:
            if not confirmation_future:
                # Should not happen if Service wired correctly
                return ToolResult(
                    tool_req.name,
                    tool_req.call_id,
                    False,
                    None,
                    0,
                    "Internal Error: Missing confirmation future",
                    error_code="missing_confirmation_future",
                    output_kind="none",
                )

            await bus.emit(
                EventTypes.TOOL_CONFIRMATION_REQUESTED,
                {
                    "tool_name": tool_req.name,
                    "parameters": tool_req.parameters,
                    "tool_call_id": tool_req.call_id,
                    "reason": "Sensitive Operation",
                },
            )

            await bus.emit(
                EventTypes.STATUS_CHANGED,
                {"status": AgentState.PAUSED, "message": "Waiting for approval..."},
            )

            # WAIT HERE
            try:
                decision_payload = (
                    await confirmation_future
                )  # Waiting for user decision indefinitely is ok.
            except asyncio.CancelledError:
                return ToolResult(
                    tool_req.name,
                    tool_req.call_id,
                    False,
                    None,
                    0,
                    "Cancelled",
                    error_code="confirmation_cancelled",
                    output_kind="none",
                )

            # Resume
            await bus.emit(
                EventTypes.STATUS_CHANGED,
                {"status": AgentState.EXECUTING, "message": "Resuming..."},
            )

            if decision_payload.decision == "rejected":
                return ToolResult(
                    tool_req.name,
                    tool_req.call_id,
                    False,
                    None,
                    0,
                    "User rejected execution",
                    error_code="user_rejected",
                    output_kind="none",
                )

    # 3. Execution
    await bus.emit(
        EventTypes.TOOL_EXECUTION_PROGRESS,
        {"tool_name": tool_req.name, "progress": 0, "message": "Starting..."},
    )

    result = await executor.execute(tool_req, registry)

    await bus.emit(
        EventTypes.TOOL_RESULT,
        {
            "tool_name": result.tool_name,
            "tool_call_id": result.call_id,
            "output": result.output,
            "success": result.success,
            "error": result.error,
            "error_code": result.error_code,
            "output_kind": result.output_kind,
            "error_details": result.error_details,
        },
    )

    await bus.emit(
        EventTypes.TOOL_EXECUTION_COMPLETE,
        {
            "tool_name": result.tool_name,
            "tool_call_id": result.call_id,
            "success": result.success,
            "duration": result.duration,
        },
    )

    return result
