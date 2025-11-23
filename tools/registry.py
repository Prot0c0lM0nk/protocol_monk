"""
Tool Registry - Auto-discovery and management of tools.
"""

import importlib
import inspect
import logging
import sys
import asyncio
from typing import Dict, List, Optional
from pathlib import Path

from .base import BaseTool, ToolResult
from agent.exceptions import ToolNotFoundError

class ToolRegistry:
    """Manages discovery, loading, and execution of tools."""
    
    def __init__(self, working_dir: Path, context_manager=None, agent_logger=None, preferred_env: str = None, venv_path: str = None):
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
            if file_path.stem.startswith("_") or file_path.stem in ["base", "registry"]:
                continue

            try:
                # Calculate module path (e.g., tools.file_operations.create_file_tool)
                relative_path = file_path.relative_to(tools_dir.parent)
                module_name = ".".join(list(relative_path.parts[:-1]) + [file_path.stem])
                
                if module_name in sys.modules:
                     module = importlib.reload(sys.modules[module_name])
                else:
                     module = importlib.import_module(module_name)
                
                self._register_tools_from_module(module)
                
            except Exception as e:
                self.logger.error(f"Failed to load tools from {file_path.name}: {e}")

    def _register_tools_from_module(self, module):
        """Helper to inspect a module and register valid tools."""
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (issubclass(obj, BaseTool) and obj != BaseTool and not inspect.isabstract(obj)):
                try:
                    # Dependency Injection
                    tool_params = inspect.signature(obj.__init__).parameters
                    dependencies = {
                        "working_dir": self.working_dir,
                        "context_manager": self.context_manager,
                        "agent_logger": self.agent_logger,
                        "preferred_env": self.preferred_env,
                        "venv_path": self.venv_path
                    }
                    
                    # Only pass what the tool asks for
                    init_args = {k: v for k, v in dependencies.items() if k in tool_params}
                    
                    tool_instance = obj(**init_args)
                    self._tools[tool_instance.schema.name] = tool_instance
                    self.logger.debug(f"Registered tool: {tool_instance.schema.name}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to instantiate tool class {name}: {e}", exc_info=True)

    async def get_tool(self, name: str) -> Optional[BaseTool]:
        async with self._lock:
            return self._tools.get(name)

    async def execute_tool(self, name: str, **kwargs) -> ToolResult:
        """Execute a tool with pre-validation."""
        tool = await self.get_tool(name)
        if not tool:
             available = list(self._tools.keys())
             raise ToolNotFoundError(tool_name=name, available_tools=available)
             
        # Parameter Validation
        required = tool.schema.required_params
        missing = [p for p in required if p not in kwargs]
        
        if missing:
            return ToolResult.invalid_params(
                f"Missing required parameters: {missing}", 
                missing_params=missing
            )
            
        try:
             if asyncio.iscoroutinefunction(tool.execute):
                 result = await tool.execute(**kwargs)
             else:
                 result = await asyncio.to_thread(tool.execute, **kwargs)
             
             if self.agent_logger:
                  self.agent_logger.log_tool_result(name, kwargs, result)
             return result
             
        except Exception as e:
              self.logger.error(f"Tool execution error '{name}'", exc_info=True)
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
            params = ", ".join(f"{k}: {v.get('type','any')}" for k,v in s.parameters.items())
            formatted.append(f"{s.name}({params}): {s.description}")
        return "\n".join(formatted)