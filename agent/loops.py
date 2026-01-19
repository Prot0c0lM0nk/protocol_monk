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

# --- PARSING STRATEGY (Spec 08) ---


class StreamParser:
    """
    State Machine for 'Locate with Regex, Parse with JSON'.
    """

    def __init__(self):
        self.buffer = ""
        self.state = "TEXT"  # TEXT | TOOL
        self.json_buffer = ""

    def feed(self, chunk: str) -> List[Dict[str, Any]]:
        """
        Ingests a chunk. Returns a list of events to emit:
        [{'type': 'chunk', 'content': '...'}, {'type': 'tool_start', 'data': '...'}]
        """
        events = []
        self.buffer += chunk

        # Simple heuristic for Phase 1: Look for code block markers
        # In a production DeepSeek/Ollama integration, we'd use specific tool tokens
        # but the spec says: Detect ```json

        while True:
            if self.state == "TEXT":
                if "```json" in self.buffer:
                    pre, post = self.buffer.split("```json", 1)
                    if pre:
                        events.append({"type": "chunk", "content": pre})
                    self.buffer = post
                    self.state = "TOOL"
                else:
                    # Safety: If buffer gets too large without marker, flush it
                    # (Keep a small horizon for split markers)
                    if len(self.buffer) > 20 and "```" not in self.buffer:
                        events.append({"type": "chunk", "content": self.buffer})
                        self.buffer = ""
                    break

            elif self.state == "TOOL":
                if "```" in self.buffer:
                    json_str, post = self.buffer.split("```", 1)
                    self.json_buffer += json_str
                    self.buffer = post
                    self.state = "TEXT"
                    # We found a block!
                    events.append({"type": "tool_block", "content": self.json_buffer})
                    self.json_buffer = ""
                else:
                    # All content is potentially JSON, hold it
                    self.json_buffer += self.buffer
                    self.buffer = ""
                    break

        return events


# --- THINKING LOOP ---


async def run_thinking_loop(
    context_history: List[Any],  # List[Message]
    provider: Any,  # BaseProvider
    bus: EventBus,
) -> AgentResponse:
    """
    Streams tokens from LLM, parses tools, and returns final response.
    """
    await bus.emit(EventTypes.THINKING_STARTED)

    parser = StreamParser()
    full_text = ""
    tool_requests: List[ToolRequest] = []

    # 1. Stream
    # Note: provider.stream_chat should yield strings
    async for chunk in provider.stream_chat(context_history):
        parse_events = parser.feed(chunk)

        for evt in parse_events:
            if evt["type"] == "chunk":
                full_text += evt["content"]
                await bus.emit(EventTypes.STREAM_CHUNK, {"chunk": evt["content"]})

            elif evt["type"] == "tool_block":
                # 2. Parse Tool JSON (Fail Fast Strategy)
                try:
                    data = json.loads(evt["content"])
                    # DeepSeek/Ollama often output a list of tools or a single object
                    if isinstance(data, dict):
                        req = _parse_tool_json(data)
                        if req:
                            tool_requests.append(req)
                    elif isinstance(data, list):
                        for item in data:
                            req = _parse_tool_json(item)
                            if req:
                                tool_requests.append(req)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse tool JSON: {evt['content']}")
                    # Fallback: Treat as text
                    full_text += f"\n```json{evt['content']}```\n"

    # Flush remaining text
    if parser.buffer and parser.state == "TEXT":
        full_text += parser.buffer
        await bus.emit(EventTypes.STREAM_CHUNK, {"chunk": parser.buffer})

    await bus.emit(EventTypes.THINKING_STOPPED)

    # 3. Finalize
    response = AgentResponse(
        content=full_text,
        tool_calls=tool_requests,
        tokens=len(full_text) // 4,  # Rough estimate
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
