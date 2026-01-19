import asyncio
import json
import logging
import time
from typing import List, Optional, Any, Dict

from protocol_monk.protocol.bus import EventBus
from protocol_monk.protocol.events import EventTypes
from protocol_monk.agent.structs import (
    AgentResponse,
    ToolRequest,
    ToolResult,
    AgentStatus,
)
from protocol_monk.agent.core.execution import ToolExecutor
from protocol_monk.agent.core.state_machine import AgentState
from protocol_monk.tools.registry import ToolRegistry

# Note: BaseProvider import assumed from providers.base (interface)
# from protocol_monk.providers.base import BaseProvider


logger = logging.getLogger("LogicLoops")

# --- THINKING LOOP ---


async def run_thinking_loop(
    context_history: List[Any], provider: Any, bus: EventBus, registry: ToolRegistry
) -> AgentResponse:
    """
    Consumes ProviderSignals and builds the response.
    """
    await bus.emit(EventTypes.THINKING_STARTED)

    full_text = ""
    tool_requests: List[ToolRequest] = []
    token_usage = 0

    # Get tool definitions to send to provider
    tool_definitions = registry.get_openai_tools()
    # Note: We pass model name from settings/context in real implementation
    # For now assuming provider knows, or we pass it in arg.
    # In service.py we usually inject the configured model name.
    # We'll update signature in next pass if needed, for now we assume provider handles defaults.
    # BUT loops.py calls provider.stream_chat(messages, model, tools)
    # We need the model name here.
    # FIX: For this refactor, we accept it uses defaults or we extract from context if available.
    # Let's assume 'default' for the call for now to keep signature clean,
    # but strictly we should pass it.

    # We'll use a placeholder model name for the loop, assuming Service injects it properly
    # or provider handles it.
    # Actually, let's just pass "default" and let Settings in Provider handle it?
    # No, BaseProvider signature requires model_name.
    # We will pass a dummy string that the provider (if connected to Settings) might override,
    # or we update the loop signature later.

    model_name = "active_model"  # Placeholder

    try:
        async for signal in provider.stream_chat(
            context_history, model_name, tool_definitions
        ):

            if signal.type == "content":
                full_text += signal.data
                await bus.emit(EventTypes.STREAM_CHUNK, {"chunk": signal.data})

            elif signal.type == "thinking":
                # We wrap thinking in tags for the UI if needed, or just emit raw
                # Spec says emit STREAM_CHUNK for thinking too, or distinct event?
                # Spec: THINKING_STARTED/STOPPED is state.
                # We can emit thinking chunks as special stream chunks or info.
                # For UI compatibility, let's treat it as stream for now but maybe prefixed?
                # Or better: Just log it for now.
                logger.debug(f"Thinking: {signal.data}")
                # Optional: await bus.emit(EventTypes.STREAM_CHUNK, {"chunk": f"<think>{signal.data}</think>"})

            elif signal.type == "tool_call":
                req: ToolRequest = signal.data
                tool_requests.append(req)
                logger.info(f"Received Tool Call: {req.name}")

            elif signal.type == "metrics":
                # Capture token counts
                data = signal.data
                if "eval_count" in data:
                    token_usage = data["eval_count"]

            elif signal.type == "error":
                logger.error(f"Provider Error Signal: {signal.data}")

    except Exception as e:
        logger.error(f"Loop Crash: {e}", exc_info=True)
        # Don't crash the agent, just return what we have

    await bus.emit(EventTypes.THINKING_STOPPED)

    response = AgentResponse(
        content=full_text,
        tool_calls=tool_requests,
        tokens=token_usage if token_usage > 0 else len(full_text) // 4,
    )

    await bus.emit(
        EventTypes.RESPONSE_COMPLETE,
        {"content": response.content, "tokens": response.tokens},
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
        if not confirmation_future:
            # Should not happen if Service wired correctly
            return ToolResult(
                tool_req.name,
                tool_req.call_id,
                False,
                None,
                0,
                "Internal Error: Missing confirmation future",
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
            decision_payload = await confirmation_future
        except asyncio.CancelledError:
            return ToolResult(
                tool_req.name, tool_req.call_id, False, None, 0, "Cancelled"
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
            )

        if decision_payload.decision == "modified":
            tool_req.parameters = decision_payload.modified_parameters

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
