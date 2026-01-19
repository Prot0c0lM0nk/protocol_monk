from abc import ABC, abstractmethod
from typing import Dict, Any
from protocol_monk.config.settings import Settings
from protocol_monk.tools.path_validator import PathValidator

class BaseTool(ABC):
    """
    Abstract parent for all tools.
    Injects:
    1. settings: The global config.
    2. path_validator: The security fence for file access.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        # ALIGNMENT FIX: Use 'workspace_root' (from settings.py)
        self.path_validator = PathValidator(self.settings.workspace_root)

    @property
    @abstractmethod
    def name(self) -> str:
        """The unique name of the tool (e.g., 'read_file')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """A short description for the LLM."""
        pass

    @property
    @abstractmethod
    def parameter_schema(self) -> Dict[str, Any]:
        """JSON schema for the tool arguments."""
        pass

    @property
    def requires_confirmation(self) -> bool:
        """
        Whether this tool requires user confirmation before execution.
        Default is False. Override in subclasses for sensitive operations.
        """
        return False

    @abstractmethod
    async def run(self, **kwargs) -> Any:
        """The execution logic."""
        pass
    def get_json_schema(self) -> Dict[str, Any]:
        """Standardized export for the LLM API."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameter_schema,
            },
        }