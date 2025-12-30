#!/usr/bin/env python3
"""
Tool Executor for Protocol Monk
===============================
Handles execution of tool calls with user confirmation and result formatting.
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
        event_bus: Optional[EventBus] = None,  # Replace ui_callback
    ):
        """
        Initialize the tool executor with registry and configuration.

        Args:
            tool_registry: Registry of available tools
            working_dir: Working directory for file operations
            auto_confirm: Whether to auto-confirm tool executions (default: False)
            event_bus: Event bus for UI interactions (default: None)
        """
        self.tool_registry = tool_registry
        self.working_dir = working_dir
        self.auto_confirm = auto_confirm
        self.event_bus = event_bus or get_event_bus()  # Use event bus
        self.logger = logging.getLogger(__name__)
        self.execution_lock = Lock()
        self._config_lock = Lock()

    async def _wait_for_confirmation(self, tool_call_id: str, timeout: float = 30.0) -> dict:
        """Wait for user confirmation via event system"""
        confirmation_future = asyncio.Future()
        
        def confirmation_handler(event_data):
            if event_data.get("tool_call_id") == tool_call_id:
                confirmation_future.set_result(event_data)
        
        # Subscribe to confirmation events
        self.event_bus.subscribe("ui.tool_confirmation", confirmation_handler)
        
        try:
            # Wait for confirmation with timeout
            return await asyncio.wait_for(confirmation_future, timeout=timeout)
        except asyncio.TimeoutError:
            # Auto-deny on timeout
            return {"approved": False, "reason": "timeout"}
        finally:
            self.event_bus.unsubscribe("ui.tool_confirmation", confirmation_handler)

    def _handle_tool_exception(self, error: Exception, action: str) -> ToolResult:
        """
        Map exceptions to ToolResults and log them appropriately.

        Args:
            error: Exception that occurred during tool execution
            action: Name of the tool that failed

        Returns:
            ToolResult: Result representing the error condition
        """
        # Note: ToolResult does not accept 'data' or metadata fields.
        # We append debug details to the output for visibility.

        if isinstance(error, ToolNotFoundError):
            self.logger.error("Tool not found: %s", action, extra={"tool_name": action})
            return ToolResult(
                success=False,
                output=f"{error.message} (Tool: {action})",
            )

        if isinstance(error, ToolExecutionError):
            self.logger.error(
                "Tool execution failed for tool %s",
                action,
                extra={"tool_name": action},
            )
            return ToolResult(
                success=False,
                output=f"{error.user_hint}\nDetails: {error.message}",
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

        # Catch-all for unexpected errors
        self.logger.error(
            "Unexpected internal error during tool execution: %s",
            action,
            exc_info=True,
            extra={"tool_name": action},
        )
        return ToolResult(
            success=False,
            output=f"An unexpected internal error occurred.\nDetails: {str(error)}",
        )

    async def _execute_tool(self, tool_call: Dict) -> ToolResult:
        """
        Execute a single tool via the registry with timeout protection.

        Args:
            tool_call: Normalized tool call dictionary

        Returns:
            ToolResult: Result of tool execution
        """
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
        except Exception as e:  # pylint: disable=broad-exception-caught
            return self._handle_tool_exception(e, action)

    def _normalize_tool_call(self, tool_call: Dict) -> Dict:
        """
        Normalize tool call formats and handle stringified arguments.
        """
        # 1. Standardize the keys first
        normalized = {}

        if "action" in tool_call and "parameters" in tool_call:
            normalized = {
                "action": tool_call["action"],
                "parameters": tool_call["parameters"],
            }
        elif "name" in tool_call and "arguments" in tool_call:
            normalized = {
                "action": tool_call["name"],
                "parameters": tool_call["arguments"],
            }
        else:
            # If it doesn't match standard patterns, it's invalid
            raise ToolInputValidationError(f"Invalid tool call format: {tool_call}")

        # 2. Safety Check: If 'parameters' is a JSON string, parse it into a dict
        if isinstance(normalized["parameters"], str):
            try:
                normalized["parameters"] = json.loads(normalized["parameters"])
            except json.JSONDecodeError:
                raise ToolInputValidationError(
                    "Tool parameters were provided as an invalid JSON string",
                    tool_name=normalized["action"],
                )

        # 3. Validation Logic (Keep your existing specific validations)
        if not normalized["action"]:
            raise ToolInputValidationError("Missing 'action' field")

        if normalized["action"] == "replace_lines":
            params = normalized["parameters"]
            if "start_line" in params and params["start_line"] < 1:
                raise ToolInputValidationError(
                    "Line numbers must be positive", tool_name="replace_lines"
                )

        return normalized

    async def _confirm_and_handle_edits(
        self, normalized: Dict, tool_call_id: str
    ) -> Tuple[Optional[Dict], Optional[ToolResult]]:
        """
        Handle UI confirmation and user modifications via event system.

        Args:
            normalized: Normalized tool call dictionary
            tool_call_id: ID of the tool call for tracking

        Returns:
            Tuple[Optional[Dict], Optional[ToolResult]]:
                (normalized_tool_call, None) -> Execution approved
                (None, ToolResult) -> User gave a suggestion (don't execute)

        Raises:
            UserCancellationError: User rejected tool execution
        """
        # Emit confirmation request event
        await self.event_bus.emit(AgentEvents.TOOL_CONFIRMATION_REQUESTED.value, {
            "tool_call": normalized,
            "tool_call_id": tool_call_id,
            "auto_confirm": self.auto_confirm
        })

        # Wait for user confirmation via event system
        confirmation_event = await self._wait_for_confirmation(tool_call_id)
        confirmation = confirmation_event.get("approved", False)

        if not confirmation:
            await self.event_bus.emit(AgentEvents.TOOL_REJECTED.value, {
                "tool_call": normalized,
                "tool_call_id": tool_call_id,
                "reason": "user_rejected"
            })
            raise UserCancellationError("User rejected tool execution")

        # Handle user modifications
        if isinstance(confirmation_event, dict) and "modified" in confirmation_event:
            modified = confirmation_event["modified"]

            if "human_suggestion" in modified:
                # Feedback mode - return result immediately, do not execute
                suggestion = modified["human_suggestion"]
                output_msg = (
                    f"User Suggestion: {suggestion}\n\n"
                    "Please modify your tool call based on this suggestion."
                )
                result = ToolResult(
                    success=False,
                    output=output_msg,
                    tool_name=modified["action"],
                )
                await self.event_bus.emit(AgentEvents.TOOL_MODIFIED.value, {
                    "original_tool_call": normalized,
                    "modified_tool_call": modified,
                    "reason": "human_suggestion"
                })
                return None, result

            # Edit mode - update normalized and continue
            normalized = modified
            await self.event_bus.emit(AgentEvents.TOOL_MODIFIED.value, {
                "original_tool_call": normalized,
                "modified_tool_call": modified,
                "reason": "user_edited"
            })

        return normalized, None

    async def _process_single_tool(
        self, tool_call: Dict
    ) -> Tuple[Optional[ToolResult], bool]:
        """
        Process the lifecycle of a single tool call.
        """
        # NEW: Extract ID early
        call_id = tool_call.get("id")

        # 1. Normalize
        try:
            normalized = self._normalize_tool_call(tool_call)
        except ToolExecutionError:
            error_msg = f"Invalid tool call format: {str(tool_call)[:100]}..."
            self.logger.warning(error_msg)
            await self.event_bus.emit(AgentEvents.ERROR.value, {
                "message": error_msg,
                "context": "tool_execution"
            })
            # Attach ID to error result
            result = ToolResult(success=False, output=error_msg)
            result.tool_call_id = call_id 
            return result, False

        if "action" not in normalized or not normalized["action"]:
            error_msg = f"Missing 'action': {str(tool_call)[:100]}..."
            self.logger.warning(error_msg)
            await self.event_bus.emit(AgentEvents.ERROR.value, {
                "message": error_msg,
                "context": "tool_execution"
            })
            result = ToolResult(success=False, output=error_msg)
            result.tool_call_id = call_id
            return result, False

        # 2. Check for Finish
        if normalized["action"] == "finish":
            await self.event_bus.emit(AgentEvents.TASK_COMPLETE.value, {
                "summary": normalized["parameters"].get("summary", "")
            })
            result = ToolResult(success=True, output="Task completed", tool_name="finish")
            result.tool_call_id = call_id
            return result, True

        # 3. Confirmation & Modification
        final_tool_call, suggestion_result = await self._confirm_and_handle_edits(
            normalized, call_id
        )

        if suggestion_result:
            suggestion_result.tool_call_id = call_id
            return suggestion_result, False

        # 4. Execute
        if final_tool_call is None:
            raise ToolExecutionError("Tool call was None after confirmation")
        
        result = await self._execute_tool(final_tool_call)

        # 5. Stamp Name & ID & Display
        if not hasattr(result, "tool_name") or not result.tool_name:
            result.tool_name = final_tool_call["action"]
            
        # NEW: Attach the ID so it flows back to the agent
        result.tool_call_id = call_id

        await self.event_bus.emit(AgentEvents.TOOL_RESULT.value, {
            "result": result,
            "tool_name": final_tool_call["action"]
        })

        return result, False

    async def execute_tool_calls(self, tool_calls: List[Dict]) -> ExecutionSummary:
        """
        Execute a list of tool calls using event system for UI interaction.

        Args:
            tool_calls: List of tool call dictionaries to execute

        Returns:
            ExecutionSummary: Summary of execution results and status
        """
        if not tool_calls:
            return ExecutionSummary()

        async with self.execution_lock:
            if not tool_calls:
                return ExecutionSummary()

            # Emit execution start
            await self.event_bus.emit(AgentEvents.TOOL_EXECUTION_START.value, {
                "count": len(tool_calls),
                "tools": [call.get("action") for call in tool_calls]
            })

            summary = ExecutionSummary()

            for i, tool_call in enumerate(tool_calls):
                # Emit progress
                await self.event_bus.emit(AgentEvents.TOOL_EXECUTION_PROGRESS.value, {
                    "current": i + 1,
                    "total": len(tool_calls),
                    "current_tool": tool_call.get("action")
                })

                result, should_finish = await self._process_single_tool(tool_call)

                if should_finish:
                    summary.should_finish = True
                    break

                if result:
                    summary.results.append(result)

            # Emit completion
            await self.event_bus.emit(AgentEvents.TOOL_EXECUTION_COMPLETE.value, {
                "summary": f"Executed {len(tool_calls)} tools",
                "had_failures": any(not r.success for r in summary.results)
            })
            
            return summary

    async def set_auto_confirm(self, value: bool):
        """
        Thread-safe update of auto-confirm setting.

        Args:
            value: New auto-confirm setting value
        """
        async with self._config_lock:
            self.auto_confirm = value
        await self.event_bus.emit(AgentEvents.AUTO_CONFIRM_CHANGED.value, {
            "value": value
        })

