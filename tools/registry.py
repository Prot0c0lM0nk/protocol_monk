from typing import Dict, List, Optional, Type
import logging
from .base import BaseTool


class ToolRegistry:
    """
    Central repository for available tools.
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._logger = logging.getLogger("ToolRegistry")

    def register(self, tool: BaseTool) -> None:
        """
        Registers a tool instance.
        """
        if tool.name in self._tools:
            self._logger.warning(f"Overwriting existing tool: {tool.name}")
        self._tools[tool.name] = tool
        self._logger.debug(f"Registered tool: {tool.name}")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Retrieves a tool by name."""
        return self._tools.get(name)

    def get_openai_tools(self) -> List[Dict]:
        """
        Returns the full list of tool definitions for the LLM API.
        This matches the structure expected by OpenAI/Anthropic/Ollama SDKs.
        """
        return [tool.get_json_schema() for tool in self._tools.values()]

    def list_tool_names(self) -> List[str]:
        return list(self._tools.keys())
