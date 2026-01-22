from typing import Dict, List, Optional, Type
import logging
from .base import BaseTool


class ToolRegistry:
    """
    Central repository for available tools.
    
    PHASE BOUNDARY:
    - INITIALIZATION PHASE: Tools are registered via register()
    - RUNTIME PHASE: Tools are read-only via get_tool(), get_openai_tools(), etc.
    
    CURRENT SAFETY:
    - register() is only called once at startup in main.py (synchronous, single-threaded)
    - All runtime access is read-only (get_tool, get_openai_tools, list_tool_names)
    - Therefore: No race condition in current architecture
    
    FUTURE CONSIDERATION:
    - If dynamic tool registration is added, this WILL become a race condition
    - The check-then-act pattern in register() is not thread-safe
    - Will need threading.Lock or asyncio.Lock at that point
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._logger = logging.getLogger("ToolRegistry")
        self._sealed: bool = False  # TODO: Implement phase boundary enforcement

    def register(self, tool: BaseTool) -> None:
        """
        Registers a tool instance.
        
        SAFETY ASSUMPTION: This is only called during initialization phase.
        If called during runtime (concurrent access), this has a race condition:
        
        RACE CONDITION (if register() is called concurrently):
        Thread A: if tool.name in self._tools: → False
        Thread B: if tool.name in self._tools: → False (still!)
        Thread A: self._tools[tool.name] = toolA
        Thread B: self._tools[tool.name] = toolB (overwrites A, no warning logged)
        
        CURRENT USAGE: Safe because register() is only called once at startup
        FUTURE USAGE: If dynamic registration is added, add:
            with self._lock:  # or async with self._lock:
                if tool.name in self._tools:
                    self._logger.warning(...)
                self._tools[tool.name] = tool
        """
        # TODO: Add phase boundary check
        # if self._sealed:
        #     raise RuntimeError("Cannot register tools after registry is sealed")
        
        if tool.name in self._tools:
            self._logger.warning(f"Overwriting existing tool: {tool.name}")
        self._tools[tool.name] = tool
        self._logger.debug(f"Registered tool: {tool.name}")

    def seal(self) -> None:
        """
        Marks the registry as sealed (read-only from this point).
        
        This encodes the phase boundary in the code:
        - After seal() is called, register() will raise an error
        - This prevents accidental late writes during runtime
        - Makes the "initialization vs runtime" contract explicit
        
        TODO: Call this in main.py after all tools are registered
        """
        self._sealed = True
        self._logger.info(f"Registry sealed with {len(self._tools)} tools")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """
        Retrieves a tool by name.
        
        SAFE: Read-only operation, no mutation of shared state.
        Dictionary get() is atomic in CPython.
        """
        return self._tools.get(name)

    def get_openai_tools(self) -> List[Dict]:
        """
        Returns the full list of tool definitions for the LLM API.
        This matches the structure expected by OpenAI/Anthropic/Ollama SDKs.
        
        SAFE: Read-only operation.
        
        NOTE: If tools were dynamically added/removed during iteration,
        this could raise RuntimeError or return inconsistent data.
        But since registry is read-only after initialization, this is safe.
        
        FUTURE: If dynamic registration is added, protect with:
            tools_copy = list(self._tools.values())
            return [tool.get_json_schema() for tool in tools_copy]
        """
        return [tool.get_json_schema() for tool in self._tools.values()]

    def list_tool_names(self) -> List[str]:
        """
        Returns list of registered tool names.
        
        SAFE: Read-only operation.
        Same considerations as get_openai_tools().
        """
        return list(self._tools.keys())
