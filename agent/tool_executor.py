#!/usr/bin/env python3
"""
Tool Executor for Protocol Monk
===============================
Handles execution of tool calls with user confirmation via Event Bus.
"""
import json
import asyncio
import logging
from asyncio import Lock
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from exceptions import (
    ToolExecutionError,
    ToolInputValidationError,
    ToolNotFoundError,
    ToolSecurityError,
    UserCancellationError,
)
from agent.interfaces import ToolResult
from config.static import settings
from agent.events import EventBus, AgentEvents, get_event_bus


@dataclass
class ExecutionSummary:
    """Summary of executing multiple tool calls."""
    results: List[ToolResult] = field(default_factory=list)
    should_finish: bool = False


class ToolExecutor:
    """Executes tool calls with human-in-the-loop confirmation."""

    def __init__(
        self,
        tool_registry,
        working_dir: Path,
        auto_confirm: bool = False,
        event_bus: Optional[EventBus] = None,
        ui=None,  # Deprecated, ignored
    ):
        self.tool_registry = tool_registry
        self.working_dir = working_dir
        self.auto_confirm = auto_confirm
        self.event_bus = event_bus or get_event_bus()
        # self.ui is intentionally removed/ignored
        self.logger = logging.getLogger(__name__)
        self.execution_lock = Lock()
        self._config_lock = Lock()

    async def _handle_tool_exception(self, error: Exception, action: str) -> ToolResult:
        """Map exceptions to ToolResults and log them appropriately."""
        if isinstance(error, ToolNotFoundError):
            self.logger.error("Tool not found: %s", action, extra={"tool_name": action})
            return ToolResult(success=False, output=f"{error.message} (Tool: {action})")

        if isinstance(error, ToolExecutionError):
            self.logger.error(
                "Tool execution failed for tool %s", action, extra={"tool_name": action}
            )
            return ToolResult(
                success=False, output=f"{error.user_hint}\nDetails: {error.message}"
            )

        if isinstance(error, ToolSecurityError):
            self.logger.warning(
                "Security violation detected for tool %s",
                action,
                extra={"tool_name": action},
            )
            return ToolResult(
                success=False,
                output=f"{error.user_hint}\nReason: {error.security_reason}",
            )

        self.logger.error(
            "Unexpected internal error: %s",
            action,
            exc_info=True,
            extra={"tool_name": action},
        )
        return ToolResult(
            success=False,
            output=f"An unexpected internal error occurred.\nDetails: {str(error)}",
        )

    async def _execute_tool(self, tool_call: Dict) -> ToolResult:
        """Execute a single tool via the registry with timeout protection."""
        action = tool_call["action"]
        parameters = tool_call["parameters"]

        try:
            return await asyncio.wait_for(
                self.tool_registry.execute_tool(action, **parameters),
                timeout=settings.model.request_timeout,
            )
        except asyncio.TimeoutError:
            raise ToolExecutionError(
                "Tool execution timed out",
                tool_name=action,
                details={"timeout_seconds": settings.model.request_timeout},
            ) from None
        except Exception as e:
            return await self._handle_tool_exception(e, action)

    def _normalize_tool_call(self, tool_call: Dict) -> Dict:
        """Normalize tool call formats from different providers."""
        normalized = {}

        # CASE 1: Custom/Ollama format: {"action": "...", "parameters": "..."}
        if "action" in tool_call and "parameters" in tool_call:
            normalized = {
                "action": tool_call["action"],
                "parameters": tool_call["parameters"],
            }

        # CASE 2: OpenAI/OpenRouter format: {"function": {"name": "...", "arguments": "..."}}
        elif "function" in tool_call:
            func = tool_call["function"]
            normalized = {
                "action": func.get("name"),
                "parameters": func.get("arguments"),
            }

        # CASE 3: Direct format: {"name": "...", "arguments": "..."}
        elif "name" in tool_call and "arguments" in tool_call:
            normalized = {
                "action": tool_call["name"],
                "parameters": tool_call["arguments"],
            }
        else:
            raise ToolInputValidationError(f"Invalid tool call format: {tool_call}")

        # Parse stringified JSON arguments (OpenAI format)
        if isinstance(normalized["parameters"], str):
            try:
                normalized["parameters"] = json.loads(normalized["parameters"])
            except json.JSONDecodeError:
                raise ToolInputValidationError(
                    "Tool parameters were provided as an invalid JSON string",
                    tool_name=normalized["action"],
                )

        return normalized

    async def _confirm_and_handle_edits(
        self, normalized: Dict, tool_call_id: str
    ) -> Tuple[Optional[Dict], Optional[ToolResult]]:
        """
        Handle confirmation via Event Bus.
        CRITICAL: Must start listening for response BEFORE emitting request,
        because the UI handles the request synchronously in the event loop.
        """
        if self.auto_confirm:
            return normalized, None

        # 1. Prepare Filter
        def match_id(data):
            return data.get("tool_call_id") == tool_call_id

        # 2. START LISTENING NOW (Before asking)
        # We create a task that subscribes immediately and waits.
        response_future = asyncio.create_task(
            self.event_bus.wait_for(
                AgentEvents.TOOL_CONFIRMATION_RESPONSE.value,
                timeout=None, # No timeout for humans
                predicate=match_id
            )
        )

        # 3. Emit Request (This blocks until UI finishes user interaction)
        await self.event_bus.emit(
            AgentEvents.TOOL_CONFIRMATION_REQUESTED.value,
            {
                "tool_call": normalized,
                "tool_call_id": tool_call_id,
                "auto_confirm": self.auto_confirm,
            },
        )

        # 4. Await the response we are already listening for
        try:
            response_data = await response_future
            
            approved = response_data.get("approved", False)
            edits = response_data.get("edits")

            if not approved:
                await self.event_bus.emit(
                    AgentEvents.TOOL_REJECTED.value,
                    {"tool_call": normalized, "tool_call_id": tool_call_id, "reason": "user_rejected"},
                )
                raise UserCancellationError("User rejected tool execution")

            if edits:
                normalized["parameters"] = edits

            return normalized, None

        except asyncio.TimeoutError:
            # Should not happen with timeout=None
            await self.event_bus.emit(
                AgentEvents.TOOL_REJECTED.value,
                {"tool_call": normalized, "tool_call_id": tool_call_id, "reason": "timeout"},
            )
            raise UserCancellationError("Confirmation timed out")

    async def _process_single_tool(
        self, tool_call: Dict
    ) -> Tuple[Optional[ToolResult], bool]:
        """Process the lifecycle of a single tool call."""
        call_id = tool_call.get("id")
        try:
            normalized = self._normalize_tool_call(tool_call)
        except ToolExecutionError:
            return ToolResult(success=False, output="Invalid format", tool_call_id=call_id), False

        if normalized["action"] == "finish":
            await self.event_bus.emit(AgentEvents.TASK_COMPLETE.value, {"summary": normalized["parameters"].get("summary", "")})
            return ToolResult(success=True, output="Task completed", tool_name="finish", tool_call_id=call_id), True

        # Calls the new event-based confirmation
        final_tool_call, suggestion_result = await self._confirm_and_handle_edits(normalized, call_id)
        if suggestion_result:
            return suggestion_result, False

        result = await self._execute_tool(final_tool_call)
        result.tool_name = final_tool_call["action"]
        result.tool_call_id = call_id

        await self.event_bus.emit(AgentEvents.TOOL_RESULT.value, {"result": result, "tool_name": result.tool_name})
        return result, False

    async def execute_tool_calls(self, tool_calls: List[Dict]) -> ExecutionSummary:
        """Execute a list of tool calls using event system for UI interaction."""
        if not tool_calls:
            return ExecutionSummary()

        async with self.execution_lock:
            await self.event_bus.emit(
                AgentEvents.TOOL_EXECUTION_START.value,
                {"count": len(tool_calls), "tools": [c.get("action") for c in tool_calls]},
            )
            summary = ExecutionSummary()
            for i, tool_call in enumerate(tool_calls):
                await self.event_bus.emit(
                    AgentEvents.TOOL_EXECUTION_PROGRESS.value,
                    {"current": i+1, "total": len(tool_calls), "current_tool": tool_call.get("action")},
                )
                result, should_finish = await self._process_single_tool(tool_call)
                if should_finish:
                    summary.should_finish = True
                    break
                if result:
                    summary.results.append(result)

            await self.event_bus.emit(
                AgentEvents.TOOL_EXECUTION_COMPLETE.value,
                {"summary": f"Executed {len(tool_calls)} tools", "had_failures": any(not r.success for r in summary.results)},
            )
            return summary

    async def set_auto_confirm(self, value: bool):
        async with self._config_lock:
            self.auto_confirm = value
        await self.event_bus.emit(AgentEvents.AUTO_CONFIRM_CHANGED.value, {"value": value})
