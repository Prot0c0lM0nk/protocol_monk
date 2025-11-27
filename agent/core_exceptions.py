from agent.exceptions import MonkBaseError

class AgentCoreError(MonkBaseError):
    """Base exception for core agent functionality."""
    pass

class OrchestrationError(AgentCoreError):
    """Raised when orchestration logic fails."""
    pass

class ConfigurationError(AgentCoreError):
    """Raised when core agent configuration is invalid."""
    pass
