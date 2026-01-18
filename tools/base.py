from abc import ABC, abstractmethod
from typing import Dict, Any, Type, List
from protocol_monk.config.settings import Settings
from protocol_monk.tools.path_validator import PathValidator


class BaseTool(ABC):
    """
    Abstract Base Class for all tools.
    Enforces atomic execution and schema generation.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        # Initialize validator with the configured workspace
        self.path_validator = PathValidator(settings.workspace_root)

    @property
    @abstractmethod
    def name(self) -> str:
        """The specific tool name (e.g., 'read_file')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Description for the LLM."""
        pass

    @property
    @abstractmethod
    def parameter_schema(self) -> Dict[str, Any]:
        """
        JSON Schema for the parameters.
        We define this manually or via Pydantic to ensure exact control.
        """
        pass

    @property
    def requires_confirmation(self) -> bool:
        """If True, the AgentService will pause for user approval."""
        return False

    @abstractmethod
    async def run(self, **kwargs) -> Any:
        """
        The Atomic Action.
        Must raise ToolError on failure, not crash.
        """
        pass

    def get_json_schema(self) -> Dict[str, Any]:
        """
        Generates the standard OpenAI/Provider-compatible function definition.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameter_schema,
            },
        }
