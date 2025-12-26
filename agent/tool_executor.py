#!/usr/bin/env python3
"""
Tool Executor for Protocol Monk
===============================
Handles execution of tool calls with user confirmation and result formatting.
"""

import asyncio
import logging
from asyncio import Lock
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from exceptions import (
    ToolExecutionError,
    ToolInputValidationError,
    ToolNotFoundError,
    ToolSecurityError,
    UserCancellationError,
)
from ui.base import ToolResult
from config.static import settings


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
        ui_callback: Optional[Callable] = None,
    ):
        """
        Initialize the tool executor with registry and configuration.

        Args:
            tool_registry: Registry of available tools
            working_dir: Working directory for file operations
            auto_confirm: Whether to auto-confirm tool executions (default: False)
            ui_callback: Callback for UI interactions (default: None)
        """
        self.tool_registry = tool_registry
        self.working_dir = working_dir
        self.auto_confirm = auto_confirm
        self.ui_callback = ui_callback
        self.logger = logging.getLogger(__name__)
        self.execution_lock = Lock()
        self._config_lock = Lock()

    async def _default_ui_callback(self, event: str, _data: Dict[str, Any]) -> Any:
        """
        Fallback callback if UI is not initialized.

        Args:
            event: UI event type
            _data: Event data dictionary

        Returns:
            Any: Response based on event type
        """
        if event == "confirm":
            return self.auto_confirm
        # For events that don't require a return value, return None
        return None

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
        Normalize different tool call formats into standard structure.
        Adds input validation for tool parameters.

        Args:
            tool_call: Raw tool call dictionary to normalize

        Returns:
            Dict: Normalized tool call with 'action' and 'parameters' keys

        Raises:
            ToolInputValidationError: If tool call format is invalid
            ToolExecutionError: If tool call format is completely invalid
        """
        # Validate required fields
        if "action" not in tool_call or not tool_call["action"]:
            raise ToolInputValidationError(
                "Missing 'action' field", tool_name=tool_call.get("name", "unknown")
            )
        if "parameters" not in tool_call:
            raise ToolInputValidationError(
                "Missing 'parameters' field",
                tool_name=tool_call.get("action", "unknown"),
            )

        # Tool-specific validation (e.g., line numbers must be positive)
        if tool_call["action"] == "replace_lines":
            params = tool_call["parameters"]
            if "start_line" in params and params["start_line"] < 1:
                raise ToolInputValidationError(
                    "Line numbers must be positive",
                    tool_name="replace_lines",
                    invalid_input=params,
                )

        if "action" in tool_call and "parameters" in tool_call:
            return tool_call
        if "name" in tool_call and "arguments" in tool_call:
            return {
                "action": tool_call["name"],
                "parameters": tool_call["arguments"],
                "reasoning": tool_call.get("reasoning", ""),
            }
        # Instead of returning None, raise an exception with details
        raise ToolExecutionError(f"Invalid tool call format: {tool_call}")

    async def _confirm_and_handle_edits(
        self, normalized: Dict
    ) -> Tuple[Optional[Dict], Optional[ToolResult]]:
        """
        Handle UI confirmation and user modifications.

        Args:
            normalized: Normalized tool call dictionary

        Returns:
            Tuple[Optional[Dict], Optional[ToolResult]]:
                (normalized_tool_call, None) -> Execution approved
                (None, ToolResult) -> User gave a suggestion (don't execute)

        Raises:
            UserCancellationError: User rejected tool execution
        """
        confirmation = await self.ui_callback(
            "confirm", {"tool_call": normalized, "auto_confirm": self.auto_confirm}
        )

        if not confirmation:
            await self.ui_callback("tool_rejected", {"tool_call": normalized})
            raise UserCancellationError("User rejected tool execution")

        # Handle user modifications
        if isinstance(confirmation, dict) and "modified" in confirmation:
            modified = confirmation["modified"]

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
                await self.ui_callback("tool_modified", {"tool_call": modified})
                return None, result

            # Edit mode - update normalized and continue
            normalized = modified
            await self.ui_callback("tool_modified", {"tool_call": modified})

        return normalized, None

    async def _process_single_tool(
        self, tool_call: Dict
    ) -> Tuple[Optional[ToolResult], bool]:
        """
        Process the lifecycle of a single tool call.
        Returns: (ToolResult, should_finish_flag)

        Args:
            tool_call: Single tool call dictionary to process

        Returns:
            Tuple[Optional[ToolResult], bool]: Tool result and finish flag

        Raises:
            ToolExecutionError: If tool call format is invalid
        """
        # 1. Normalize
        try:
            normalized = self._normalize_tool_call(tool_call)
        except ToolExecutionError:
            error_msg = f"Invalid tool call format: {str(tool_call)[:100]}..."
            self.logger.warning(error_msg)
            await self.ui_callback("tool_error", {"error": error_msg})
            return ToolResult(success=False, output=error_msg), False

        if "action" not in normalized or not normalized["action"]:
            error_msg = f"Missing 'action': {str(tool_call)[:100]}..."
            self.logger.warning(error_msg)
            await self.ui_callback("tool_error", {"error": error_msg})
            return ToolResult(success=False, output=error_msg), False

        # 2. Check for Finish
        if normalized["action"] == "finish":
            await self.ui_callback(
                "task_complete",
                {"summary": normalized["parameters"].get("summary", "")},
            )
            # Return a success result with finish message instead of None
            return (
                ToolResult(success=True, output="Task completed", tool_name="finish"),
                True,
            )

        # 3. Confirmation & Modification (Refactored)
        final_tool_call, suggestion_result = await self._confirm_and_handle_edits(
            normalized
        )

        if suggestion_result:
            return suggestion_result, False

        # 4. Execute - Check that final_tool_call is not None
        if final_tool_call is None:
            raise ToolExecutionError("Tool call was None after confirmation")
        result = await self._execute_tool(final_tool_call)

        # 5. Stamp Name & Display
        if not hasattr(result, "tool_name") or not result.tool_name:
            result.tool_name = final_tool_call["action"]
        await self.ui_callback(
            "result", {"result": result, "tool_name": final_tool_call["action"]}
        )

        return result, False

    async def execute_tool_calls(self, tool_calls: List[Dict]) -> ExecutionSummary:
        """
        Execute a list of tool calls using async UI callback.

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

            summary = ExecutionSummary()
            await self.ui_callback("execution_start", {"count": len(tool_calls)})

            for i, tool_call in enumerate(tool_calls):
                await self.ui_callback(
                    "progress", {"current": i + 1, "total": len(tool_calls)}
                )

                result, should_finish = await self._process_single_tool(tool_call)

                if should_finish:
                    summary.should_finish = True
                    break

                if result:
                    summary.results.append(result)

            await self.ui_callback("execution_complete", {})
            return summary

    async def set_auto_confirm(self, value: bool):
        """
        Thread-safe update of auto-confirm setting.

        Args:
            value: New auto-confirm setting value
        """
        async with self._config_lock:
            self.auto_confirm = value
        await self.ui_callback("auto_confirm_changed", {"value": value})
