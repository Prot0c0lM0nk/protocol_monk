#!/usr/bin/env python3
"""
Tool Executor for Protocol Monk
===============================
Handles execution of tool calls with user confirmation and result formatting.
"""

from pathlib import Path
from typing import List, Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from asyncio import Lock
import logging

from ui.base import ToolResult
from agent.exceptions import UserCancellationError

@dataclass
class ExecutionSummary:
    """Summary of executing multiple tool calls."""
    results: List[ToolResult] = field(default_factory=list)
    should_finish: bool = False


class ToolExecutor:
    def __init__(
        self,
        tool_registry,
        working_dir: Path,
        auto_confirm: bool = False,
        ui_callback: Optional[Callable] = None
    ):
        self.tool_registry = tool_registry
        self.working_dir = working_dir
        self.auto_confirm = auto_confirm
        self.ui_callback = ui_callback or self._default_ui_callback
        self.logger = logging.getLogger(__name__)
        self._config_lock = Lock()
    
    async def _default_ui_callback(self, event: str, data: Dict[str, Any]) -> Any:
        """Fallback callback if UI is not initialized."""
        if event == "confirm":
            return self.auto_confirm
        return None

    async def _execute_tool(self, tool_call: Dict) -> ToolResult:
        """Execute a single tool via the registry."""
        action = tool_call["action"]
        parameters = tool_call["parameters"]
        
        try:
            # Call tool via registry
            # The Registry handles the complexity of finding and running the tool
            result = await self.tool_registry.execute_tool(action, **parameters)
            return result
            
        except Exception as e:
            # Log the full error internally
            self.logger.error(
                f"Tool execution failed: {action}", 
                exc_info=True,
                extra={"parameters": parameters}
            )
            
            # Return a clean error to the LLM so it can self-correct
            return ToolResult(
                success=False,
                output=f"Tool execution failed: {str(e)}",
                tool_name=action
            )

    async def execute_tool_calls(self, tool_calls: List[Dict]) -> ExecutionSummary:
        """
        Execute a list of tool calls using async UI callback.
        """
        if not tool_calls:
            return ExecutionSummary()

        summary = ExecutionSummary()
        
        # Notify UI of execution start
        await self.ui_callback("execution_start", {"count": len(tool_calls)})

        for i, tool_call in enumerate(tool_calls):
            # Notify UI of progress
            await self.ui_callback("progress", {"current": i+1, "total": len(tool_calls)})
            
            # Normalize tool call format
            normalized = self._normalize_tool_call(tool_call)
            if not normalized:
                error_msg = f"Invalid tool call format: {str(tool_call)[:100]}..."
                self.logger.warning(error_msg)
                
                result = ToolResult(success=False, output=error_msg)
                summary.results.append(result)
                await self.ui_callback("tool_error", {"error": error_msg})
                continue

            # Check for finish tool
            if normalized["action"] == "finish":
                summary.should_finish = True
                await self.ui_callback("task_complete", {
                    "summary": normalized["parameters"].get("summary", "")
                })
                break 
            
            # Ask UI for confirmation
            confirmation = await self.ui_callback("confirm", {
                "tool_call": normalized,
                "auto_confirm": self.auto_confirm
            })
            
            if not confirmation:
                await self.ui_callback("tool_rejected", {"tool_call": normalized})
                raise UserCancellationError("User rejected tool execution")
            
            # Handle user modifications
            if isinstance(confirmation, dict) and "modified" in confirmation:
                modified = confirmation["modified"]
                
                if "human_suggestion" in modified:
                    # User provided feedback instead of executing
                    suggestion_result = ToolResult(
                        success=False,
                        output=f"User Suggestion: {modified['human_suggestion']}\n\nPlease modify your tool call based on this suggestion.",
                        tool_name=modified["action"]
                    )
                    summary.results.append(suggestion_result)
                    await self.ui_callback("tool_modified", {"tool_call": modified})
                    continue 
                else:
                    # User edited parameters
                    normalized = modified
                    await self.ui_callback("tool_modified", {"tool_call": modified})
            
            # Execute
            result = await self._execute_tool(normalized)
            
            # --- CRITICAL FIX: Stamp the tool name ---
            # The tool itself doesn't know its registry name, so the Executor 
            # (which holds the 'normalized' dict) must attach it here.
            # This ensures the Core loop has the 'tool_name' attribute it expects.
            if not hasattr(result, 'tool_name') or not result.tool_name:
                result.tool_name = normalized["action"]
            
            summary.results.append(result)
            
            # Display result
            await self.ui_callback("result", {
                "result": result,
                "tool_name": normalized["action"]
            })

        await self.ui_callback("execution_complete", {})
        return summary

    def _normalize_tool_call(self, tool_call: Dict) -> Optional[Dict]:
        """Normalize different tool call formats into standard structure."""
        # Standard format
        if "action" in tool_call and "parameters" in tool_call:
            return tool_call # Already normalized
        # Anthropic format
        if "name" in tool_call and "arguments" in tool_call:
            return {
                "action": tool_call["name"],
                "parameters": tool_call["arguments"],
                "reasoning": tool_call.get("reasoning", "")
            }
        return None

    async def set_auto_confirm(self, value: bool):
        """Thread-safe update of auto-confirm setting."""
        async with self._config_lock:
            self.auto_confirm = value
        await self.ui_callback("auto_confirm_changed", {"value": value})