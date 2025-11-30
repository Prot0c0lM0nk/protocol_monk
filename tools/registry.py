"""
Tool Registry - Auto-discovery and management of tools.
"""

import inspect

import asyncio
import importlib
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.tools.exceptions import ToolNotFoundError
from tools.base import BaseTool, ToolResult


class ToolRegistry:
    """Manages discovery, loading, and execution of tools."""

    def __init__(
        self,
        working_dir: Path,
        context_manager=None,
        agent_logger=None,
        preferred_env: str = None,
        venv_path: str = None,
    ):
        self.working_dir = working_dir
        self.context_manager = context_manager
        self.agent_logger = agent_logger
        self.preferred_env = preferred_env
        self.venv_path = venv_path
        self.logger = logging.getLogger(__name__)
        self._tools: Dict[str, BaseTool] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

    async def async_initialize(self):
        """Initialize async components."""
        if self._initialized:
            return
        await asyncio.to_thread(self._discover_tools)
        self._initialized = True

    def _discover_tools(self):
        """Auto-discover and register tools from the 'tools' directory."""
        tools_dir = Path(__file__).parent

        for file_path in tools_dir.glob("**/*.py"):
            if self._should_skip_file(file_path):
                continue
            self._load_module_from_path(file_path, tools_dir)

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped during discovery."""
        return file_path.stem.startswith("_") or file_path.stem in [
            "base",
            "registry",
            "exceptions",
        ]

    def _load_module_from_path(self, file_path: Path, tools_dir: Path):
        """Load a single module from a file path."""
        try:
            relative_path = file_path.relative_to(tools_dir.parent)
            module_name = ".".join(list(relative_path.parts[:-1]) + [file_path.stem])

            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)

            self._register_tools_from_module(module)

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("Failed to load tools from %s: %s", file_path.name, e)

    def _register_tools_from_module(self, module):
        """Inspect a module and register valid tools."""
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if self._is_valid_tool_class(obj):
                self._register_single_tool(obj)

    def _is_valid_tool_class(self, obj) -> bool:
        """Check if class is a valid BaseTool subclass."""
        return (
            issubclass(obj, BaseTool)
            and obj != BaseTool
            and not inspect.isabstract(obj)
        )

    def _register_single_tool(self, tool_class):
        """Instantiate and register a single tool class."""
        try:
            dependencies = self._get_tool_dependencies()
            tool_params = inspect.signature(tool_class.__init__).parameters

            # Only pass what the tool asks for
            init_args = {k: v for k, v in dependencies.items() if k in tool_params}

            tool_instance = tool_class(**init_args)
            self._tools[tool_instance.schema.name] = tool_instance
            self.logger.debug("Registered tool: %s", tool_instance.schema.name)

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error(
                "Failed to instantiate tool class %s: %s",
                tool_class.__name__,
                e,
                exc_info=True,
            )

    def _get_tool_dependencies(self) -> Dict[str, Any]:
        """Create dependency dictionary for injection."""
        return {
            "working_dir": self.working_dir,
            "context_manager": self.context_manager,
            "agent_logger": self.agent_logger,
            "preferred_env": self.preferred_env,
            "venv_path": self.venv_path,
        }

    async def get_tool(self, name: str) -> Optional[BaseTool]:
        async with self._lock:
            return self._tools.get(name)

    async def execute_tool(self, name: str, **kwargs) -> ToolResult:
        """Execute a tool with pre-validation."""
        tool = await self.get_tool(name)
        if not tool:
            available = list(self._tools.keys())
            raise ToolNotFoundError(tool_name=name, available_tools=available)

        missing = self._validate_tool_params(tool, kwargs)
        if missing:
            return ToolResult.invalid_params(
                f"Missing required parameters: {missing}", missing_params=missing
            )

        return await self._run_tool_execution(tool, name, kwargs)

    def _validate_tool_params(self, tool: BaseTool, kwargs: Dict) -> List[str]:
        """Check for missing required parameters."""
        required = tool.schema.required_params
        return [p for p in required if p not in kwargs]

    async def _run_tool_execution(
        self, tool: BaseTool, name: str, kwargs: Dict
    ) -> ToolResult:
        """Handle the actual execution and logging."""
        try:
            if asyncio.iscoroutinefunction(tool.execute):
                result = await tool.execute(**kwargs)
            else:
                result = await asyncio.to_thread(tool.execute, **kwargs)

            if self.agent_logger:
                self.agent_logger.log_tool_result(name, kwargs, result)
            return result

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("Tool execution error '%s'", name, exc_info=True)
            return ToolResult.internal_error(f"Tool execution error: {str(e)}")

    # --- Helper Methods ---
    async def list_tools(self) -> List[str]:
        async with self._lock:
            return list(self._tools.keys())

    async def get_formatted_tool_schemas(self) -> str:
        async with self._lock:
            schemas = [t.schema for t in self._tools.values()]

        if not schemas:
            return "No tools available."

        formatted = []
        for s in schemas:
            params = ", ".join(
                f"{k}: {v.get('type','any')}" for k, v in s.parameters.items()
            )
            formatted.append(f"{s.name}({params}): {s.description}")
        return "\n".join(formatted)
