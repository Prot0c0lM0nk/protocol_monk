import asyncio
import time
import logging
from typing import Any

from protocol_monk.agent.structs import ToolRequest, ToolResult
from protocol_monk.tools.registry import ToolRegistry
from protocol_monk.exceptions.tools import ToolError


class ToolExecutor:
    """
    The Safe Runner.
    Isolates tool execution from the main loop logic.
    Handles timeouts and crashes.
    """

    def __init__(self, timeout_seconds: int = 60):
        self._timeout = timeout_seconds
        self._logger = logging.getLogger("ToolExecutor")

    async def execute(self, request: ToolRequest, registry: ToolRegistry) -> ToolResult:
        """
        Executes a tool request atomically.
        """
        start_time = time.time()
        tool = registry.get_tool(request.name)

        # 1. Validation Barrier
        if not tool:
            return ToolResult(
                tool_name=request.name,
                call_id=request.call_id,
                success=False,
                output=None,
                error=f"Tool not found: {request.name}",
                duration=0.0,
            )

        try:
            # 2. Atomic Execution with Timeout
            self._logger.info(f"Executing {request.name} (ID: {request.call_id})")

            # Using wait_for to enforce strict timeout
            result = await asyncio.wait_for(
                tool.run(**request.parameters), timeout=self._timeout
            )

            duration = time.time() - start_time
            return ToolResult(
                tool_name=request.name,
                call_id=request.call_id,
                success=True,
                output=result,
                duration=duration,
                error=None,
            )

        except asyncio.TimeoutError:
            duration = time.time() - start_time
            self._logger.error(f"Tool {request.name} timed out after {self._timeout}s")
            return ToolResult(
                tool_name=request.name,
                call_id=request.call_id,
                success=False,
                output=None,
                duration=duration,
                error=f"Execution timed out after {self._timeout} seconds.",
            )

        except ToolError as e:
            # Domain specific errors (safe)
            duration = time.time() - start_time
            self._logger.warning(f"Tool {request.name} failed: {e.user_hint}")
            return ToolResult(
                tool_name=request.name,
                call_id=request.call_id,
                success=False,
                output=None,
                duration=duration,
                error=e.user_hint,
            )

        except Exception as e:
            # Unexpected crashes (catch-all barrier)
            duration = time.time() - start_time
            self._logger.exception(f"Unexpected error in tool {request.name}")
            return ToolResult(
                tool_name=request.name,
                call_id=request.call_id,
                success=False,
                output=None,
                duration=duration,
                error=f"System Error: {str(e)}",
            )
