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

# pylint: disable=no-name-in-module
from exceptions import ToolNotFoundError
from tools.base import BaseTool, ToolResult


class ToolRegistry:
    """Manages discovery, loading, and execution of tools."""

    def __init__(
        self, working_dir: Path, context_manager=None, agent_logger=None, **kwargs
    ):
        """
        Initialize the registry.

        Args:
            working_dir: The base directory for tool execution.
            context_manager: Optional context manager instance.
            agent_logger: Optional logger for agent operations.
            **kwargs: Config options like 'preferred_env', 'venv_path'.
        """
        self.working_dir = working_dir
        self.context_manager = context_manager
        self.agent_logger = agent_logger
        self.env_config = {
            "preferred_env": kwargs.get("preferred_env"),
            "venv_path": kwargs.get("venv_path"),
        }
        self.logger = logging.getLogger(__name__)
        self._tools: Dict[str, BaseTool] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        self._init_lock: asyncio.Lock = asyncio.Lock()  # NEW: protects initialization
        self._initialized = False

    async def async_initialize(self):
        """Initialize async components with protection against concurrent calls."""
        async with self._init_lock:  # NEW: prevent concurrent initialization
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
        """
        Check if file should be skipped during discovery.

        Args:
            file_path: The path of the file to check.

        Returns:
            bool: True if the file should be skipped.
        """
        return file_path.stem.startswith("_") or file_path.stem in [
            "base",
            "registry",
            "exceptions",
        ]

    def _load_module_from_path(self, file_path: Path, tools_dir: Path):
        """
        Load a single module from a file path.

        Args:
            file_path: The absolute path to the module file.
            tools_dir: The root tools directory.
        """
        try:
            relative_path = file_path.relative_to(tools_dir.parent)
            # Create module dot path (e.g. tools.file_operations.read_tool)
            parts = list(relative_path.parts[:-1]) + [file_path.stem]
            module_name = ".".join(parts)

            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                module = importlib.import_module(module_name)

            self._register_tools_from_module(module)

        except Exception as e:  # pylint: disable=broad-exception-caught
            self.logger.error("Failed to load tools from %s: %s", file_path.name, e)

    def _register_tools_from_module(self, module):
        """
        Inspect a module and register valid tools.

        Args:
            module: The loaded python module to inspect.
        """
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if self._is_valid_tool_class(obj):
                self._register_single_tool(obj)

    def _is_valid_tool_class(self, obj) -> bool:
        """
        Check if class is a valid BaseTool subclass.

        Args:
            obj: The class object to inspect.

        Returns:
            bool: True if valid tool class, False otherwise.
        """
        return (
            issubclass(obj, BaseTool)
            and obj != BaseTool
            and not inspect.isabstract(obj)
        )

    def _register_single_tool(self, tool_class):
        """
        Instantiate and register a single tool class.

        Args:
            tool_class: The class of the tool to register.
        """
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
        """
        Create dependency dictionary for injection.

        Returns:
            Dict[str, Any]: A dictionary of dependencies.
        """
        return {
            "working_dir": self.working_dir,
            "context_manager": self.context_manager,
            "agent_logger": self.agent_logger,
            "preferred_env": self.env_config["preferred_env"],
            "venv_path": self.env_config["venv_path"],
        }

    async def get_tool(self, name: str) -> Optional[BaseTool]:
        """
        Retrieve a tool by name.

        Args:
            name: The name of the tool.

        Returns:
            Optional[BaseTool]: The tool instance or None.
        """
        async with self._lock:
            return self._tools.get(name)

    async def execute_tool(self, name: str, **kwargs) -> ToolResult:
        """
        Execute a tool with pre-validation.

        Args:
            name: The name of the tool to execute.
            **kwargs: Arguments to pass to the tool.

        Returns:
            ToolResult: The result of the execution.

        Raises:
            ToolNotFoundError: If the tool name is not registered.
        """
        tool = await self.get_tool(name)
        if not tool:
            available = list(self._tools.keys())
            raise ToolNotFoundError(f"Tool '{name}' not found. Available: {available}")

        missing = self._validate_tool_params(tool, kwargs)
        if missing:
            return ToolResult.invalid_params(
                f"Missing required parameters: {missing}", missing_params=missing
            )

        return await self._run_tool_execution(tool, name, kwargs)

    def _validate_tool_params(self, tool: BaseTool, kwargs: Dict) -> List[str]:
        """
        Check for missing required parameters.

        Args:
            tool: The tool instance.
            kwargs: The arguments provided for execution.

        Returns:
            List[str]: A list of missing parameter names.
        """
        required = tool.schema.required_params
        return [p for p in required if p not in kwargs]

    async def _run_tool_execution(
        self, tool: BaseTool, name: str, kwargs: Dict
    ) -> ToolResult:
        """
        Handle the actual execution and logging.

        Args:
            tool: The tool instance.
            name: The name of the tool.
            kwargs: The execution arguments.

        Returns:
            ToolResult: The execution result.
        """
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
        """
        List all registered tool names.

        Returns:
            List[str]: A list of tool names.
        """
        async with self._lock:
            return list(self._tools.keys())

    async def get_formatted_tool_schemas(self) -> str:
        """
        Get a string representation of all tool schemas.

        Returns:
            str: The formatted schemas string.
        """
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
